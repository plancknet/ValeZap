from __future__ import annotations

from queue import Empty
from datetime import datetime, timezone
import uuid
from urllib.parse import urlparse

import httpx

from flask import (
    Blueprint,
    Response,
    current_app,
    jsonify,
    render_template,
    request,
    stream_with_context,
)
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from .database import db_session
from .models import ChatMessage
from .sse import broker


api_bp = Blueprint("api", __name__)
pages_bp = Blueprint("pages", __name__)



ALLOWED_WEBHOOK_HOSTS = {"n8n-n8n-webhook.jhbg9t.easypanel.host"}


def dispatch_external_webhook(
    session_id: str,
    message: str,
    vendor_id: str | None = None,
    room_name: str | None = None,
) -> dict[str, str] | None:
    webhook_url = current_app.config.get("EXTERNAL_WEBHOOK_URL", "").strip()
    if not webhook_url:
        current_app.logger.info("External webhook skipped: no URL configured")
        return None

    parsed = urlparse(webhook_url)
    if parsed.scheme != "https" or parsed.netloc not in ALLOWED_WEBHOOK_HOSTS:
        current_app.logger.warning(
            "External webhook blocked: host %s is not allowed", parsed.netloc
        )
        return None

    payload = {
        "session": session_id,
        "message": message,
    }
    if vendor_id:
        payload["vendedor"] = vendor_id
    if room_name:
        payload["nom_sala"] = room_name
    current_app.logger.info(
        "Dispatching external webhook to %s for session=%s vendor=%s sala=%s",
        webhook_url,
        session_id,
        vendor_id or "-",
        room_name or "-",
    )

    try:
        with httpx.Client(timeout=5.0) as client:
            response = client.post(
                webhook_url, json=payload, follow_redirects=False
            )
            response.raise_for_status()
    except httpx.HTTPError as exc:
        current_app.logger.exception(
            "External webhook request failed: %s", exc
        )
        return None

    current_app.logger.info(
        "External webhook responded with status %s",
        response.status_code,
    )

    try:
        data = response.json()
    except ValueError:
        current_app.logger.warning("External webhook returned non JSON body")
        return None

    reply_text = _extract_nested_value(
        data,
        ("message", "mensagem", "reply", "text", "conteudo", "content"),
    )
    if not reply_text:
        current_app.logger.info("External webhook did not return reply text")
        return None

    if reply_text.lower() == "workflow was started":
        current_app.logger.info("External webhook returned placeholder message; ignoring")
        return None

    raw_reply_session = _extract_nested_value(
        data,
        ("sessao", "session", "session_id"),
    ) or session_id
    reply_session = _normalize_uuid(raw_reply_session, session_id, label="session")

    current_app.logger.info(
        "External webhook produced reply for session=%s",
        reply_session,
    )

    return {
        "session_id": reply_session,
        "message": reply_text,
    }



def _normalize_uuid(value: str, fallback: str, *, label: str) -> str:
    try:
        uuid.UUID(value)
        return value
    except (ValueError, AttributeError, TypeError):
        if value and value != fallback:
            current_app.logger.info(
                "External webhook reply %s value '%s' is invalid; using fallback",
                label,
                value,
            )
        return fallback



def _pick_payload_value(payload: object, *keys: str) -> str:
    if isinstance(payload, str):
        candidate = payload.strip()
        return candidate if candidate else ""

    if isinstance(payload, dict):
        for key in keys:
            if key not in payload:
                continue
            value = payload.get(key)
            candidate = _pick_payload_value(value, *keys)
            if candidate:
                return candidate
        for value in payload.values():
            candidate = _pick_payload_value(value, *keys)
            if candidate:
                return candidate
        return ""

    if isinstance(payload, (list, tuple)):
        for item in payload:
            candidate = _pick_payload_value(item, *keys)
            if candidate:
                return candidate
        return ""

    if payload is None:
        return ""

    candidate = str(payload).strip()
    return candidate if candidate else ""


def _extract_nested_value(payload: object, keys: tuple[str, ...]) -> str:
    if isinstance(payload, str):
        candidate = payload.strip()
        return candidate if candidate else ""

    if isinstance(payload, dict):
        for key in keys:
            if key in payload:
                candidate = _extract_nested_value(payload[key], keys)
                if candidate:
                    return candidate
        for value in payload.values():
            candidate = _extract_nested_value(value, keys)
            if candidate:
                return candidate
        return ""

    if isinstance(payload, (list, tuple)):
        for item in payload:
            candidate = _extract_nested_value(item, keys)
            if candidate:
                return candidate
        return ""

    if payload is None:
        return ""

    candidate = str(payload).strip()
    return candidate if candidate else ""


@pages_bp.route("/")
def index() -> str:
    return render_template(
        "index.html",
        client_api_key=current_app.config["CLIENT_API_KEY"],
    )


@api_bp.route("/health", methods=["GET"])
def healthcheck() -> Response:
    return jsonify({"status": "ok"})


@api_bp.route("/api/messages", methods=["GET"])
def list_messages() -> Response:
    session_id = request.args.get("sessao") or request.args.get("session_id")

    if not session_id:
        return jsonify({"error": "Missing sessao parameter"}), 400

    stmt = (
        select(ChatMessage)
        .where(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.created_at.asc())
    )

    messages = [message.to_dict() for message in db_session.execute(stmt).scalars().all()]
    return jsonify({"messages": messages})


@api_bp.route("/api/messages/stream", methods=["GET"])
def stream_messages() -> Response:
    session_id = request.args.get("sessao") or request.args.get("session_id")

    if not session_id:
        return jsonify({"error": "Missing sessao parameter"}), 400

    queue = broker.subscribe(session_id)
    last_seen_at = datetime.now(timezone.utc)
    seen_ids: set[str] = set()

    def event_stream():
        nonlocal last_seen_at
        try:
            while True:
                try:
                    message = queue.get(timeout=5)
                    message_id = str(message.get("id") or "")
                    if message_id and message_id in seen_ids:
                        continue
                    created_at_iso = message.get("created_at")
                    if created_at_iso:
                        try:
                            last_seen_at = max(
                                last_seen_at,
                                datetime.fromisoformat(created_at_iso),
                            )
                        except ValueError:
                            pass
                    if message_id:
                        seen_ids.add(message_id)
                    yield broker.format_sse(message)
                except Empty:
                    try:
                        stmt = (
                            select(ChatMessage)
                            .where(
                                ChatMessage.session_id == session_id,
                                ChatMessage.created_at > last_seen_at,
                            )
                            .order_by(ChatMessage.created_at.asc())
                        )
                        new_messages = (
                            db_session.execute(stmt).scalars().all()
                        )
                        if new_messages:
                            for db_message in new_messages:
                                message_dict = db_message.to_dict()
                                message_id = str(message_dict.get("id") or "")
                                if message_id and message_id in seen_ids:
                                    continue
                                if message_id:
                                    seen_ids.add(message_id)
                                last_seen_at = max(
                                    last_seen_at,
                                    db_message.created_at or last_seen_at,
                                )
                                yield broker.format_sse(message_dict)
                        else:
                            yield ": keep-alive\n\n"
                    except SQLAlchemyError:
                        db_session.rollback()
                        current_app.logger.exception(
                            "Failed to fetch messages for SSE fallback"
                        )
                        yield ": keep-alive\n\n"
        finally:
            broker.unsubscribe(session_id, queue)

    response = Response(stream_with_context(event_stream()), mimetype="text/event-stream")
    response.headers["Cache-Control"] = "no-cache"
    response.headers["X-Accel-Buffering"] = "no"
    return response


@api_bp.route("/functions/v1/webhook-valezap", methods=["POST"])
def webhook_valezap() -> Response:
    payload = request.get_json(silent=True) or {}
    current_app.logger.info(
        "Webhook request received with keys=%s",
        sorted(payload.keys()) if isinstance(payload, dict) else type(payload),
    )

    sessao = _pick_payload_value(payload, "sessao", "session", "session_id")
    mensagem = _pick_payload_value(payload, "mensagem", "message", "content", "texto")
    vendedor = _pick_payload_value(payload, "vendedor", "vendor")
    nome_sala = _pick_payload_value(payload, "nom_sala", "nome_sala", "sala")

    current_app.logger.info(
        "Webhook payload parsed: session=%s vendor=%s sala=%s message_length=%s",
        sessao or "-",
        vendedor or "-",
        nome_sala or "-",
        len(mensagem) if mensagem else 0,
    )

    if not sessao or not mensagem:
        current_app.logger.warning(
            "Webhook rejected: missing required fields (session=%s, has_message=%s)",
            bool(sessao),
            bool(mensagem),
        )
        return jsonify({"error": "Parametros obrigatorios: sessao, mensagem"}), 400

    provided_key = (
        request.headers.get("x-api-key")
        or (request.headers.get("authorization") or "").replace("Bearer ", "")
    )
    service_key = current_app.config.get("SERVICE_API_KEY")
    client_key = current_app.config.get("CLIENT_API_KEY")

    body_service_key = ""
    if isinstance(payload, dict):
        raw_service_key = (
            payload.get("service_api_key")
            or payload.get("serviceKey")
            or payload.get("service-token")
            or payload.get("serviceToken")
        )
        if raw_service_key is not None:
            body_service_key = str(raw_service_key).strip()

    is_service_request = bool(service_key) and (
        provided_key == service_key or body_service_key == service_key
    )

    if not is_service_request and client_key and provided_key == client_key:
        current_app.logger.debug("Webhook authenticated with client key")

    if body_service_key:
        payload.pop("service_api_key", None)
        payload.pop("serviceKey", None)
        payload.pop("service-token", None)
        payload.pop("serviceToken", None)

    current_app.logger.info(
        "Webhook authentication evaluated: service_mode=%s (header=%s body_token=%s)",
        is_service_request,
        bool(provided_key and provided_key == service_key),
        bool(body_service_key),
    )

    if not is_service_request:
        current_app.logger.info(
            "Webhook treated as user workflow; awaiting external reply"
        )

    try:
        if is_service_request:
            current_app.logger.info(
                "Persisting service message for session=%s",
                sessao,
            )
            message_record = ChatMessage(
                session_id=sessao,
                message=mensagem,
                is_from_user=False,
            )
            db_session.add(message_record)
            db_session.commit()
            message_dict = message_record.to_dict()
            broker.publish(message_dict)
            current_app.logger.info(
                "Service message published id=%s", message_dict.get("id")
            )
            return jsonify({"success": True, "data": message_dict}), 200

        current_app.logger.info(
            "Persisting user message for session=%s",
            sessao,
        )
        user_message = ChatMessage(
            session_id=sessao,
            message=mensagem,
            is_from_user=True,
        )
        db_session.add(user_message)
        db_session.commit()
        user_dict = user_message.to_dict()
        current_app.logger.info(
            "User message stored id=%s; evaluating auto-reply pipeline",
            user_dict.get("id"),
        )

        auto_reply_mode = (
            current_app.config.get("AUTO_REPLY_MODE", "").strip().lower()
        )
        reply_data: dict[str, str] | None = None

        if auto_reply_mode in {"webhook", "external"}:
            current_app.logger.info(
                "Auto-reply mode '%s' enabled; forwarding message to external webhook",
                auto_reply_mode,
            )
            reply_data = dispatch_external_webhook(sessao, mensagem, vendedor, nome_sala)
        else:
            current_app.logger.debug(
                "Auto-reply disabled (mode=%s); forwarding webhook without rendering reply",
                auto_reply_mode or "unset",
            )
            dispatch_external_webhook(sessao, mensagem, vendedor, nome_sala)

        response_payload: dict[str, object] = {
            "sessao": sessao,
            "mensagem": mensagem,
            "record": user_dict,
        }
        if vendedor:
            response_payload["vendedor"] = vendedor
        if nome_sala:
            response_payload["nom_sala"] = nome_sala
        status_code = 202

        if reply_data:
            current_app.logger.info(
                "Reply received from external webhook for session=%s",
                reply_data["session_id"],
            )
            reply_message = ChatMessage(
                session_id=reply_data["session_id"],
                message=reply_data["message"],
                is_from_user=False,
            )
            db_session.add(reply_message)
            db_session.commit()
            bot_dict = reply_message.to_dict()
            broker.publish(bot_dict)
            response_payload["reply"] = bot_dict
            status_code = 200
            current_app.logger.info(
                "Reply stored and published id=%s", bot_dict.get("id")
            )
        else:
            current_app.logger.info("External webhook returned no reply")

        return jsonify({"success": True, "data": response_payload}), status_code

    except SQLAlchemyError:
        db_session.rollback()
        current_app.logger.exception("Erro ao processar mensagem")
        return jsonify({"error": "Erro interno ao registrar mensagem"}), 500


