import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os

def send_email(recipient, subject, body):
    # Configure your SMTP server settings.
    # For example, using Gmail:
    smtp_server = "smtp.gmail.com"
    smtp_port = 587
    sender_email = "ekpko22@gmail.com"
    sender_password = "bxns sluo narb uirz"

    # Create a multipart message and set headers
    msg = MIMEMultipart()
    msg["From"] = sender_email
    msg["To"] = recipient
    msg["Subject"] = subject

    # Add body to email
    msg.attach(MIMEText(body, "plain"))
    
    try:
        # Connect to the server and send the email
        server = smtplib.SMTP(smtp_server, smtp_port)
        server.starttls()  # Secure the connection
        server.login(sender_email, sender_password)
        server.sendmail(sender_email, recipient, msg.as_string())
        server.quit()
        print("Email sent successfully to", recipient)
        return True
    except Exception as e:
        print("Error sending email:", e)
        return False
