from flask import Flask, request

app = Flask(__name__)

@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.get_json()  # Get the incoming JSON data
    
    # Process the data from the webhook
    # You can perform any actions you need here

    return 'Webhook received!', 200

if __name__ == '__main__':
    app.run(debug=True)
