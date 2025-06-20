import os
import logging
from flask import Flask, request, Response
from openai import OpenAI, APIError as OpenAIAPIError # More specific exception
from twilio.rest import Client
from twilio.base.exceptions import TwilioRestException # More specific exception
from twilio.twiml.messaging_response import MessagingResponse

# --- Configuration Loading ---
try:
    import config
except ImportError:
    logging.critical("Configuration file config.py not found. Please create it from config.py.template.")
    exit(1) # Critical error, exit

# --- Logging Setup ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- Flask App Initialization ---
app = Flask(__name__)

# --- Service Clients Initialization ---
openai_client = None
if not hasattr(config, 'OPENAI_API_KEY') or config.OPENAI_API_KEY == "YOUR_OPENAI_API_KEY" or not config.OPENAI_API_KEY:
    logging.error("OpenAI API key is not configured in config.py.")
else:
    try:
        openai_client = OpenAI(api_key=config.OPENAI_API_KEY)
        logging.info("OpenAI client initialized successfully.")
    except Exception as e:
        logging.error(f"Error initializing OpenAI client: {e}")

twilio_client = None
if not hasattr(config, 'TWILIO_ACCOUNT_SID') or config.TWILIO_ACCOUNT_SID == "YOUR_TWILIO_ACCOUNT_SID" or    not hasattr(config, 'TWILIO_AUTH_TOKEN') or config.TWILIO_AUTH_TOKEN == "YOUR_TWILIO_AUTH_TOKEN" or    not hasattr(config, 'TWILIO_WHATSAPP_NUMBER') or config.TWILIO_WHATSAPP_NUMBER == "whatsapp:YOUR_TWILIO_WHATSAPP_NUMBER":
    logging.error("Twilio credentials (Account SID, Auth Token, or WhatsApp Number) are not fully configured in config.py.")
else:
    try:
        twilio_client = Client(config.TWILIO_ACCOUNT_SID, config.TWILIO_AUTH_TOKEN)
        logging.info("Twilio client initialized successfully.")
    except TwilioRestException as e:
        logging.error(f"Error initializing Twilio client: {e}")
    except Exception as e: # Catch any other unexpected error during Twilio client init
        logging.error(f"Unexpected error initializing Twilio client: {e}")


@app.route("/whatsapp", methods=["POST"])
def whatsapp_reply():
    """Receive and respond to incoming WhatsApp messages."""
    # For production, you should validate Twilio requests.
    # from twilio.request_validator import RequestValidator
    # validator = RequestValidator(config.TWILIO_AUTH_TOKEN)
    # if not validator.validate(request.url, request.form, request.headers.get('X-Twilio-Signature')):
    #     logging.warning("Twilio request validation failed.")
    #     return Response("Request validation failed", status=403)

    incoming_msg_body = request.values.get("Body", "").strip()
    from_number = request.values.get("From", "")

    logging.info(f"Incoming message from {from_number}: '{incoming_msg_body}'")

    resp = MessagingResponse()
    reply_msg = resp.message()

    if not incoming_msg_body:
        logging.warning(f"Empty message body received from {from_number}.")
        reply_msg.body("Por favor, envie uma mensagem com conteúdo.")
        return str(resp)

    # Check if clients are initialized
    if not openai_client:
        logging.error("OpenAI client not available for message processing.")
        reply_msg.body("Desculpe, o serviço de IA não está configurado ou disponível no momento.")
        return str(resp)

    if not twilio_client:
        # This check is more for completeness; if Twilio client failed, we wouldn't receive the message.
        # However, if it was initialized but became unusable later, this would be relevant.
        logging.error("Twilio client not available for sending reply.")
        # Cannot send Twilio reply if client is down, so this is more for server log
        return Response("Internal server error: Twilio client unavailable", status=500)


    try:
        prompt = (
            "Você é um assistente de IA para advogados brasileiros. "
            "Responda a perguntas e forneça informações úteis para o dia a dia de um advogado no Brasil. "
            "Seja conciso e direto ao ponto. Se a pergunta não for relacionada a direito ou advocacia no Brasil, "
            "informe que você só pode ajudar com tópicos jurídicos brasileiros.\n\n"
            f"Pergunta do usuário: {incoming_msg_body}"
        )

        chat_completion = openai_client.chat.completions.create(
            messages=[
                {
                    "role": "system",
                    "content": "Você é um assistente de IA para advogados brasileiros."
                },
                {
                    "role": "user",
                    "content": incoming_msg_body,
                }
            ],
            model="gpt-3.5-turbo",
        )

        ai_response = chat_completion.choices[0].message.content
        logging.info(f"OpenAI response for {from_number}: '{ai_response}'")
        reply_msg.body(ai_response)

    except OpenAIAPIError as e:
        logging.error(f"OpenAI API error for {from_number}: {e}")
        reply_msg.body("Desculpe, ocorreu um erro ao contatar o serviço de IA. Tente novamente mais tarde.")
    except Exception as e:
        logging.error(f"Unexpected error processing message for {from_number} with OpenAI: {e}", exc_info=True)
        reply_msg.body("Desculpe, ocorreu um erro inesperado ao processar sua mensagem.")

    return str(resp)

if __name__ == "__main__":
    logging.info("Starting Flask development server...")
    logging.info("To receive messages, expose this server (e.g., using ngrok) and configure Twilio webhook.")
    # Ensure host is 0.0.0.0 to be accessible externally if needed (e.g. in a container)
    app.run(host="0.0.0.0", port=os.environ.get("PORT", 5000), debug=False) # Debug=False for better logging
