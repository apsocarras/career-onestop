
# A very simple Flask Hello World app for you to get started with...

# from flask import Flask

# app = Flask(__name__)

from flask import Flask, request
from modules import main

app = Flask(__name__)

@app.route('/')
def hello_world():

    return 'This is just so I know the site is live when I click on the link.'

@app.route('/webhook', methods=['GET', 'POST','HEAD'])
def webhook():
    if request.method == 'HEAD': # for setting up webhook with SM API
        return '', 200
    elif request.method in ('POST', 'GET'):
        data = main()
        return data, 200

if __name__ == '__main__':
    app.run(debug=True)
