from flask import Flask, request

app = Flask(__name__)

@app.route('/auth/callback', methods=['GET'])
def oauth_callback():
    # Handle the OAuth2 callback here
    authorization_code = request.args.get('code')
    
    # You can now use the authorization code to obtain an access token from SurveyMonkey

    return f'Authorization Code: {authorization_code}'

if __name__ == '__main__':
    app.run(debug=True)
