from flask import Flask
import requests 
import yaml 

# Avoid Oauth 2.0 setup and temporary long-term credential creation for now 
with open("api-key.yaml", "r") as file:
     access_token = yaml.full_load(file)['access-token']

headers = {

    'Authorizaqtion': f'Bearer {access_token}'

}


app = Flask(__name__)

@app.route('/')
def hello():
    return 'Hello, World!'

if __name__ == '__main__':
    app.run()
