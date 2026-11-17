import os
import smtplib
import ssl
from email.message import EmailMessage
from urllib.parse import urlsplit


def send_verification(address, token):
    host = os.environ.get('WORKOUTPLAN_SMTP_HOST')
    sender = os.environ.get('WORKOUTPLAN_SMTP_FROM')
    base = os.environ.get('WORKOUTPLAN_PUBLIC_URL', '').rstrip('/')
    url = urlsplit(base)
    if not host or not sender or url.scheme not in ('http', 'https') or not url.netloc:
        raise RuntimeError('Отправка писем пока не настроена')
    link = f'{base}/#verify-email={token}'
    message = EmailMessage()
    message['From'] = sender
    message['To'] = address
    message['Subject'] = 'ПланТренировок — подтвердите почту'
    message.set_content(f'Подтвердите адрес электронной почты по ссылке:\n{link}\n\n'
                        'Ссылка действует 24 часа и используется один раз.')
    try:
        with smtplib.SMTP(host, int(os.environ.get('WORKOUTPLAN_SMTP_PORT', '587')), timeout=5) as smtp:
            smtp.starttls(context=ssl.create_default_context())
            username = os.environ.get('WORKOUTPLAN_SMTP_USER')
            if username:
                smtp.login(username, os.environ.get('WORKOUTPLAN_SMTP_PASSWORD', ''))
            smtp.send_message(message)
    except (OSError, ValueError) as error:
        raise RuntimeError('Не удалось отправить письмо. Попробуйте позже.') from error
