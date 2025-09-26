from __future__ import annotations

from datetime import datetime


WELCOME_MESSAGE = "Olá! Sou o ValeZap. Como posso te ajudar hoje?"


def generate_auto_reply(message: str) -> str:
    """Generate a simple rule-based response."""
    normalized = message.strip().lower()

    if not normalized:
        return "Não entendi sua mensagem. Pode tentar novamente?"

    if any(greeting in normalized for greeting in ("ola", "olá", "oi", "bom dia", "boa tarde")):
        return "Oi! 😊 Conte comigo para informações sobre vales, benefícios e suporte."

    if "vale" in normalized and "transporte" in normalized:
        return (
            "Você pode consultar seu saldo de vale-transporte pelo aplicativo oficial ou pelo portal do colaborador."
        )

    if "cartao" in normalized or "cartão" in normalized:
        return (
            "Se o seu cartão apresentar problemas, recomendo tentar reaproximar após alguns minutos. "
            "Caso persista, posso orientar como solicitar um novo."
        )

    if "obrigado" in normalized or "valeu" in normalized:
        return "De nada! Se precisar de algo mais é só chamar."

    if "tchau" in normalized or "até" in normalized:
        return "Até mais! Sempre que quiser continuar é só enviar uma mensagem."

    if "horario" in normalized or "horário" in normalized:
        return "Nosso atendimento humano funciona das 8h às 18h em dias úteis."

    current_time = datetime.now().strftime("%H:%M")
    return (
        "Recebi sua mensagem às {time}. Em instantes um de nossos atendentes virtuais retorna "
        "com mais detalhes!"
    ).format(time=current_time)