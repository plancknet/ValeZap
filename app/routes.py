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
from .services.responses import generate_auto_reply
from .sse import broker


api_bp = Blueprint("api", __name__)
pages_bp = Blueprint("pages", __name__)



ALLOWED_WEBHOOK_HOSTS = {"n8n-n8n-webhook.jhbg9t.easypanel.host"}


def dispatch_external_webhook(session_id: str, player_id: str, message: str) -> None:
    webhook_url = current_app.config.get("EXTERNAL_WEBHOOK_URL", "").strip()
    if not webhook_url:
        return

    parsed = urlparse(webhook_url)
    if parsed.scheme != "https" or parsed.netloc not in ALLOWED_WEBHOOK_HOSTS:
        current_app.logger.warning("Skipping external webhook: URL not allowed")
        return

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
    sessao = (payload.get("sessao") or "").strip()
    player = (payload.get("player") or "").strip()
    mensagem = (payload.get("mensagem") or "").strip()

    if not sessao or not player or not mensagem:
        return jsonify({"error": "Parâmetros obrigatórios: sessao, player, mensagem"}), 400

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

        dispatch_external_webhook(sessao, player, mensagem)

        reply_content = generate_auto_reply(mensagem)
        bot_message = ChatMessage(
            session_id=sessao,
            player_id=player,
            message=reply_content,
            is_from_user=False,
        )
        db_session.add(bot_message)
        db_session.commit()
        bot_dict = bot_message.to_dict()
        broker.publish(bot_dict)

        return (
            jsonify(
                {
                    "success": True,
                    "data": {
                        "sessao": sessao,
                        "player": player,
                        "mensagem": mensagem,
                        "reply": bot_dict,
                    },
                }
            ),
            200,
        )

    except SQLAlchemyError:
        db_session.rollback()
        current_app.logger.exception("Erro ao processar mensagem")
        return jsonify({"error": "Erro interno ao registrar mensagem"}), 500
