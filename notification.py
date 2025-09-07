# /usr/bin/env python
# Download the twilio-python library from twilio.com/docs/libraries/python
import os
from dotenv import load_dotenv
from twilio.rest import Client

load_dotenv() 

# Find these values at https://twilio.com/user/account
# To set up environmental variables, see http://twil.io/secure
account_sid = os.environ['TWILIO_ACCOUNT_SID']
auth_token = os.environ['TWILIO_AUTH_TOKEN']

client = Client(account_sid, auth_token)

def send_sms(recipient_phone, message):
    client.api.account.messages.create(
    to=recipient_phone,
    from_="+16065321904",
    body=message)

def send_email(email: str, subject: str, body: str):
    # TODO: Implémenter SMTP ou API Sendgrid
    pass
