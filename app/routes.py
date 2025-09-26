from __future__ import annotations

from queue import Empty
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


def dispatch_external_webhook(session_id: str, player_id: str, message: str) -> dict[str, str] | None:
    webhook_url = current_app.config.get("EXTERNAL_WEBHOOK_URL", "").strip()
    if not webhook_url:
        return None

    parsed = urlparse(webhook_url)
    if parsed.scheme != "https" or parsed.netloc not in ALLOWED_WEBHOOK_HOSTS:
        current_app.logger.warning("Skipping external webhook: URL not allowed")
        return None

    payload = {
        "session": session_id,
        "player": player_id,
        "message": message,
    }

    try:
        with httpx.Client(timeout=5.0) as client:
            response = client.post(
                webhook_url, json=payload, follow_redirects=False
            )
            response.raise_for_status()
    except httpx.HTTPError:
        current_app.logger.exception("Failed to call external webhook")
        return None

    try:
        data = response.json()
    except ValueError:
        return None

    raw_reply = data.get("message") or data.get("mensagem") or data.get("reply")
    reply_text = str(raw_reply).strip() if raw_reply is not None else ""
    if not reply_text:
        return None

    raw_session = data.get("session") or data.get("sessao") or data.get("session_id")
    reply_session = str(raw_session).strip() if raw_session is not None else session_id
    reply_session = reply_session or session_id

    raw_player = data.get("player") or data.get("player_id")
    reply_player = str(raw_player).strip() if raw_player is not None else player_id
    reply_player = reply_player or player_id

    return {
        "session_id": reply_session,
        "player_id": reply_player,
        "message": reply_text,
    }




def _pick_payload_value(payload: dict[str, object], *keys: str) -> str:
    for key in keys:
        if key not in payload:
            continue
        value = payload.get(key)
        if value is None:
            continue
        candidate = value.strip() if isinstance(value, str) else str(value).strip()
        if candidate:
            return candidate
    return ""


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
    player_id = request.args.get("player") or request.args.get("player_id")

    if not session_id or not player_id:
        return jsonify({"error": "Missing sessao and player parameters"}), 400

    stmt = (
        select(ChatMessage)
        .where(
            ChatMessage.session_id == session_id,
            ChatMessage.player_id == player_id,
        )
        .order_by(ChatMessage.created_at.asc())
    )

    messages = [message.to_dict() for message in db_session.execute(stmt).scalars().all()]
    return jsonify({"messages": messages})


@api_bp.route("/api/messages/stream", methods=["GET"])
def stream_messages() -> Response:
    session_id = request.args.get("sessao") or request.args.get("session_id")
    player_id = request.args.get("player") or request.args.get("player_id")

    if not session_id or not player_id:
        return jsonify({"error": "Missing sessao and player parameters"}), 400

    queue = broker.subscribe(session_id, player_id)

    def event_stream():
        try:
            while True:
                try:
                    message = queue.get(timeout=15)
                    yield broker.format_sse(message)
                except Empty:
                    yield ": keep-alive\n\n"
        finally:
            broker.unsubscribe(session_id, player_id, queue)

    response = Response(stream_with_context(event_stream()), mimetype="text/event-stream")
    response.headers["Cache-Control"] = "no-cache"
    response.headers["X-Accel-Buffering"] = "no"
    return response


@api_bp.route("/functions/v1/webhook-valezap", methods=["POST"])
def webhook_valezap() -> Response:
    payload = request.get_json(silent=True) or {}
    sessao = _pick_payload_value(payload, "sessao", "session", "session_id")
    player = _pick_payload_value(payload, "player", "player_id")
    mensagem = _pick_payload_value(payload, "mensagem", "message", "content", "texto")

    if not sessao or not player or not mensagem:
        return jsonify({"error": "Parametros obrigatorios: sessao, player, mensagem"}), 400

    provided_key = (
        request.headers.get("x-api-key")
        or (request.headers.get("authorization") or "").replace("Bearer ", "")
    )
    service_key = current_app.config.get("SERVICE_API_KEY")

    is_service_request = bool(service_key) and provided_key == service_key

    try:
        if is_service_request:
            message_record = ChatMessage(
                session_id=sessao,
                player_id=player,
                message=mensagem,
                is_from_user=False,
            )
            db_session.add(message_record)
            db_session.commit()
            message_dict = message_record.to_dict()
            broker.publish(message_dict)
            return jsonify({"success": True, "data": message_dict}), 200

        user_message = ChatMessage(
            session_id=sessao,
            player_id=player,
            message=mensagem,
            is_from_user=True,
        )
        db_session.add(user_message)
        db_session.commit()
        user_dict = user_message.to_dict()

        reply_data = dispatch_external_webhook(sessao, player, mensagem)

        response_payload: dict[str, object] = {
            "sessao": sessao,
            "player": player,
            "mensagem": mensagem,
            "record": user_dict,
        }
        status_code = 202

        if reply_data:
            reply_message = ChatMessage(
                session_id=reply_data["session_id"],
                player_id=reply_data["player_id"],
                message=reply_data["message"],
                is_from_user=False,
            )
            db_session.add(reply_message)
            db_session.commit()
            bot_dict = reply_message.to_dict()
            broker.publish(bot_dict)
            response_payload["reply"] = bot_dict
            status_code = 200

        return jsonify({"success": True, "data": response_payload}), status_code

    except SQLAlchemyError:
        db_session.rollback()
        current_app.logger.exception("Erro ao processar mensagem")
        return jsonify({"error": "Erro interno ao registrar mensagem"}), 500
