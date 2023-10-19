

class SurveyResponse:
    """Class for associating SurveyMonkey survey responses to CareerOneStop API responses"""
    def __init__(self, sm_response, cos_request, cos_response):
        self.sm_response = sm_response
        self.cos_request = cos_request
        self.cos_response = cos_response

    def greet(self):
        print(f"Hello, my name is {self.name} and I am {self.age} years old.")

    def have_birthday(self):
        self.age += 1
        print(f"Happy birthday! I am now {self.age} years old.")
