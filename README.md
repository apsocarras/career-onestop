### Project Overview:

We want to administer this [career services survey](https://www.careeronestop.org/Developers/WebAPI/Occupation/list-occupations-skills-match.aspx) offline using a Qualtrics survey on IPad. 

We need to add the questions from career services into Qualtrics, collect the answers, and export them once online via the career services API integration. The API will then email the survey taker with recommendations for suitable career paths.  

1. Create a Qualtrics survey

2. Download the Qualtrics survey to Qualtrics IPad app 
  
3. Collect survey responses offline

4. Export survey responses 
   
   1. **Initial export**
      * *Option A*: Have a script running on IPad in the background which exports the results (answers + user email) automatically to cloud storage when back online using the Qualtrics API.
      * *Option B*: User manually exports the survey results and drag/drops the file on IPad to a designated storage bucket, with the upload completing once they are back online. 
        * See if Qualtrics
   2. **Export to career services**: Host a serverless function which reads the data from this bucket and sends it to career services API
   * <ins>Recommendations</ins>: 
     * Store data in cloud storage intermediary rather than sending directly to career services API. This preserves state for re-tries in case there are any errors, and optionally allows for warehousing (useful for tracking/avoiding repeat submissions and for trend analysis). 
     * Take *Option B* for much easier development and to avoid issues with installation, maintenance, and updates/versioning.

5. Configure API integration for email responses to user.  
   * Multiple APIs through Career services -- [here](https://www.careeronestop.org/Developers/WebAPI/SkillsMatcher/submit-skills.aspx) is the correct one for our purposes.


![workflow-diagram](img/cloud-workflow.resized.png)

### APIs

* [Skills submit API](https://www.careeronestop.org/Developers/WebAPI/SkillsMatcher/submit-skills.aspx) 
  * Submit request containing JSON ([example](https://www.careeronestop.org/TridionMultimedia/skills-matcher-json-data.json)) of work-related skills and your personal rating in each (from Beginner to Basic)
  * Receive a JSON response with a list of matching jobs  
    * See `data/skills-submit-api/` for an example request (same as above) and response retrieved via the [API explorer](https://api.careeronestop.org/api-explorer/home/index/SkillsMatcher_Submit_SKA)
* [Get skills API](https://www.careeronestop.org/Developers/WebAPI/SkillsMatcher/get-skills.aspx)
  * Receive a JSON representation of the survey questions and answer values
    * See `data/get-skills-api/response.json`, also retrieved from API explorer

Register [here](https://www.careeronestop.org/Developers/WebAPI/registration.aspx) for API key and user id