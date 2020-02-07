# -*- coding: utf-8 -*-
from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals

from rasa_core_sdk import Tracker
from rasa_core_sdk.executor import CollectingDispatcher

from typing import Dict, Text, Any, List

import requests
from rasa_core_sdk import Action
from rasa_core_sdk.events import SlotSet, FollowupAction
from rasa_core_sdk.forms import FormAction
import json

# We use the medicare.gov database to find information about 3 different
# healthcare facility types, given a city name, zip code or facility ID
# the identifiers for each facility type is given by the medicare database
# rbry-mqwu is for hospitals
# b27b-2uc7 is for nursing homes
# 9wzi-peqs is for home health agencies

ENDPOINTS = {
    "base": "https://data.medicare.gov/resource/{}.json",
    "rbry-mqwu": {
        "city_query": "?city={}",
        "zip_code_query": "?zip_code={}",
        "id_query": "?provider_id={}"
    },
    "b27b-2uc7": {
        "city_query": "?provider_city={}",
        "zip_code_query": "?provider_zip_code={}",
        "id_query": "?federal_provider_number={}"
    },
    "9wzi-peqs": {
        "city_query": "?city={}",
        "zip_code_query": "?zip={}",
        "id_query": "?provider_number={}"
    }
}

FACILITY_TYPES = {
    "hospital":
        {
            "name": "hospital",
            "resource": "rbry-mqwu"
        },
    "nursing_home":
        {
            "name": "nursing home",
            "resource": "b27b-2uc7"
        },
    "home_health":
        {
            "name": "home health agency",
            "resource": "9wzi-peqs"
        }
}


def _create_path(base: Text, resource: Text,
                 query: Text, values: Text) -> Text:
    """Creates a path to find provider using the endpoints."""

    if isinstance(values, list):
        return (base + query).format(
            resource, ', '.join('"{0}"'.format(w) for w in values))
    else:
        return (base + query).format(resource, values)


def _find_facilities(location: Text, resource: Text) -> List[Dict]:
    """Returns json of facilities matching the search criteria."""

    if str.isdigit(location):
        full_path = _create_path(ENDPOINTS["base"], resource,
                                 ENDPOINTS[resource]["zip_code_query"],
                                 location)
    else:
        full_path = _create_path(ENDPOINTS["base"], resource,
                                 ENDPOINTS[resource]["city_query"],
                                 location.upper())

    results = requests.get(full_path).json()
    return results


def _resolve_name(facility_types, resource) ->Text:
    for key, value in facility_types.items():
        if value.get("resource") == resource:
            return value.get("name")
    return ""


class FindFacilityTypes(Action):
    """This action class allows to display buttons for each facility type
    for the user to chose from to fill the facility_type entity slot."""

    def name(self) -> Text:
        """Unique identifier of the action"""

        return "find_facility_types"

    def run(self,
            dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List:

        buttons = []
        for t in FACILITY_TYPES:
            facility_type = FACILITY_TYPES[t]
            payload = "/inform{\"facility_type\": \"" + facility_type.get(
                "resource") + "\"}"

            buttons.append(
                {"title": "{}".format(facility_type.get("name").title()),
                 "payload": payload})

        # TODO: update rasa core version for configurable `button_type`
        dispatcher.utter_button_template("utter_greet", buttons, tracker)
        return []


class FindHealthCareAddress(Action):
    """This action class retrieves the address of the user's
    healthcare facility choice to display it to the user."""

    def name(self) -> Text:
        """Unique identifier of the action"""

        return "find_healthcare_address"

    def run(self,
            dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict]:

        facility_type = tracker.get_slot("facility_type")
        healthcare_id = tracker.get_slot("facility_id")
        full_path = _create_path(ENDPOINTS["base"], facility_type,
                                 ENDPOINTS[facility_type]["id_query"],
                                 healthcare_id)
        results = requests.get(full_path).json()
        if results:
            selected = results[0]
            if facility_type == FACILITY_TYPES["hospital"]["resource"]:
                address = "{}, {}, {} {}".format(selected["address"].title(),
                                                 selected["city"].title(),
                                                 selected["state"].upper(),
                                                 selected["zip_code"].title())
            elif facility_type == FACILITY_TYPES["nursing_home"]["resource"]:
                address = "{}, {}, {} {}".format(selected["provider_address"].title(),
                                                 selected["provider_city"].title(),
                                                 selected["provider_state"].upper(),
                                                 selected["provider_zip_code"].title())
            else:
                address = "{}, {}, {} {}".format(selected["address"].title(),
                                                 selected["city"].title(),
                                                 selected["state"].upper(),
                                                 selected["zip"].title())

            return [SlotSet("facility_address", address)]
        else:
            print("No address found. Most likely this action was executed "
                  "before the user choose a healthcare facility from the "
                  "provided list. "
                  "If this is a common problem in your dialogue flow,"
                  "using a form instead for this action might be appropriate.")

            return [SlotSet("facility_address", "not found")]


class FacilityForm(FormAction):
    """Custom form action to fill all slots required to find specific type
    of healthcare facilities in a certain city or zip code."""

    def name(self) -> Text:
        """Unique identifier of the form"""

        return "facility_form"

    @staticmethod
    def required_slots(tracker: Tracker) -> List[Text]:
        """A list of required slots that the form has to fill"""

        return ["facility_type", "location"]

    def slot_mappings(self) -> Dict[Text, Any]:
        return {"facility_type": self.from_entity(entity="facility_type",
                                                  intent=["inform",
                                                          "search_provider"]),
                "location": self.from_entity(entity="location",
                                             intent=["inform",
                                                     "search_provider"])}

    def submit(self,
               dispatcher: CollectingDispatcher,
               tracker: Tracker,
               domain: Dict[Text, Any]
               ) -> List[Dict]:
        """Once required slots are filled, print buttons for found facilities"""

        location = tracker.get_slot('location')
        facility_type = tracker.get_slot('facility_type')

        results = _find_facilities(location, facility_type)
        button_name = _resolve_name(FACILITY_TYPES, facility_type)
        if len(results) == 0:
            dispatcher.utter_message(
                "Sorry, we could not find a {} in {}.".format(button_name,
                                                              location.title()))
            return []

        buttons = []
        # limit number of results to 3 for clear presentation purposes
        for r in results[:3]:
            if facility_type == FACILITY_TYPES["hospital"]["resource"]:
                facility_id = r.get("provider_id")
                name = r["hospital_name"]
            elif facility_type == FACILITY_TYPES["nursing_home"]["resource"]:
                facility_id = r["federal_provider_number"]
                name = r["provider_name"]
            else:
                facility_id = r["provider_number"]
                name = r["provider_name"]

            payload = "/inform{\"facility_id\":\"" + facility_id + "\"}"
            buttons.append(
                {"title": "{}".format(name.title()), "payload": payload})

        if len(buttons) == 1:
            message = "Here is a {} near you:".format(button_name)
        else:
            if button_name == "home health agency":
                button_name = "home health agencie"
            message = "Here are {} {}s near you:".format(len(buttons),
                                                         button_name)

        # TODO: update rasa core version for configurable `button_type`
        dispatcher.utter_button_message(message, buttons)

        return []


class ActionChitchat(Action):
    """Returns the chitchat utterance dependent on the intent"""

    def name(self) -> Text:
        """Unique identifier of the action"""

        return "action_chitchat"

    def run(self,
            dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List:

        intent = tracker.latest_message['intent'].get('name')

        # retrieve the correct chitchat utterance dependent on the intent
        if intent in ['ask_builder', 'ask_weather', 'ask_howdoing',
                      'ask_howold', 'ask_languagesbot', 'ask_restaurant',
                      'ask_time', 'ask_wherefrom', 'ask_whoami',
                      'handleinsult', 'telljoke', 'ask_whatismyname']:
            dispatcher.utter_template('utter_' + intent, tracker)

        return []
import requests
import json

class ApiAction1(Action):
    def name(self):
        return "action_play_new_song"

    def run(self, dispatcher, tracker, domain):
        url = "https://devru-gaana-v1.p.rapidapi.com/newReleases.php"

        headers = {
        'x-rapidapi-host': "devru-gaana-v1.p.rapidapi.com",
        'x-rapidapi-key': "cd60813deemsh9ba8b7139e55dd4p13b503jsn82c4f4eae495"   
        }

        response = requests.request("GET", url, headers=headers)

        #print(response.text)
   
        
        #display(Image(response[0], height=550, width=520))
        dispatcher.utter_message(response.text)
class ApiAction2(Action):
    def name(self):
        return "action_play_popular_song"

    def run(self, dispatcher, tracker, domain):
        url = "https://devru-gaana-v1.p.rapidapi.com/popularTracks.php"

        headers = {
        'x-rapidapi-host': "devru-gaana-v1.p.rapidapi.com",
        'x-rapidapi-key': "cd60813deemsh9ba8b7139e55dd4p13b503jsn82c4f4eae495"
        }

        response = requests.request("GET", url, headers=headers)

        #print(response.text)
   
        
        #display(Image(response[0], height=550, width=520))
        dispatcher.utter_message(response.text)
class ApiAction3(Action):
    def name(self):
        return "action_get_cricket_scorecard1"

    def run(self, dispatcher, tracker, domain):
        url = "https://dev132-cricket-live-scores-v1.p.rapidapi.com/scorecards.php"
        
        querystring = {"seriesid":"2141","matchid":"43431"}

        headers = {
        'x-rapidapi-host': "dev132-cricket-live-scores-v1.p.rapidapi.com",
        'x-rapidapi-key': "cd60813deemsh9ba8b7139e55dd4p13b503jsn82c4f4eae495"   
        }

        response = requests.request("GET", url, headers=headers,params=querystring)
        data = json.loads(response.text)
	#print(len(data))
        for i in range(0,len(data["fullScorecard"]["innings"][0]["batsmen"])-2):
            print("name of the player: "+str(data["fullScorecard"]["innings"][0]["batsmen"][i]["name"]))
            print("runs "+str(data["fullScorecard"]["innings"][0]["batsmen"][i]["runs"]))
            print("strikerate "+str(data["fullScorecard"]["innings"][0]["batsmen"][i]["strikeRate"]))
            print("kul maare gaye chauke "+ str(data["fullScorecard"]["innings"][0]["batsmen"][i]["fours"]))
            print("kul maare gaye chhake "+str(data["fullScorecard"]["innings"][0]["batsmen"][i]["sixes"]))
  

class ApiAction3(Action):
    def name(self):
        return "action_get_cricket_scorecard1"

    def run(self, dispatcher, tracker, domain):
        url = "https://dev132-cricket-live-scores-v1.p.rapidapi.com/scorecards.php"
        
        querystring = {"seriesid":"2141","matchid":"43432"}

        headers = {
        'x-rapidapi-host': "dev132-cricket-live-scores-v1.p.rapidapi.com",
        'x-rapidapi-key': "cd60813deemsh9ba8b7139e55dd4p13b503jsn82c4f4eae495"   
        }

        response = requests.request("GET", url, headers=headers,params=querystring)
        data = json.loads(response.text)
	#print(len(data))
        for i in range(0,len(data["fullScorecard"]["innings"][0]["batsmen"])-2):
            print("name of the player: "+str(data["fullScorecard"]["innings"][0]["batsmen"][i]["name"]))
            print("runs "+str(data["fullScorecard"]["innings"][0]["batsmen"][i]["runs"]))
            print("strikerate "+str(data["fullScorecard"]["innings"][0]["batsmen"][i]["strikeRate"]))
            print("kul maare gaye chauke "+ str(data["fullScorecard"]["innings"][0]["batsmen"][i]["fours"]))
            print("kul maare gaye chhake "+str(data["fullScorecard"]["innings"][0]["batsmen"][i]["sixes"]))
  




class ApiAction4(Action):
    def name(self):
        return "action_get_cricket_match_details"

    def run(self, dispatcher, tracker, domain):
        url = "https://dev132-cricket-live-scores-v1.p.rapidapi.com/matches.php"
        querystring = {"completedlimit":"5","inprogresslimit":"5","upcomingLimit":"5"}
        headers = {
        'x-rapidapi-host': "dev132-cricket-live-scores-v1.p.rapidapi.com",
        'x-rapidapi-key': "cd60813deemsh9ba8b7139e55dd4p13b503jsn82c4f4eae495"   
        }

        response = requests.request("GET", url, headers=headers,params=querystring)

        #print(response.text)
   
        
        #display(Image(response[0], height=550, width=520))
        dispatcher.utter_message(response.text)
class ApiAction5(Action):
    def name(self):
        return "action_get_cricket_commentary"

    def run(self, dispatcher, tracker, domain):
        url = "https://dev132-cricket-live-scores-v1.p.rapidapi.com/comments.php"
        querystring = {"seriesid":"2141","matchid":"43434"}

        headers = {
        'x-rapidapi-host': "dev132-cricket-live-scores-v1.p.rapidapi.com",
        'x-rapidapi-key': "cd60813deemsh9ba8b7139e55dd4p13b503jsn82c4f4eae495"   
        }

        response = requests.request("GET", url, headers=headers, params=querystring)

        #print(response.text)
   
        
        #display(Image(response[0], height=550, width=520))
        dispatcher.utter_message(response.text)
class ApiAction6(Action):
    def name(self):
        return "action_get_train_details_rj"

    def run(self, dispatcher, tracker, domain):
        url = "https://trains.p.rapidapi.com/"

        payload = "{\"search\":\"Rajdhani\"}"
        headers = {
        'x-rapidapi-host': "trains.p.rapidapi.com",
        'x-rapidapi-key': "cd60813deemsh9ba8b7139e55dd4p13b503jsn82c4f4eae495",
        'content-type': "application/json",
        'accept': "application/json"
        }

        response = requests.request("POST", url, data=payload, headers=headers)
        data = json.loads(response.text)
        #print(len(data))
        for i in range(0,len(data)):
          dispatcher.utter_message( "Train_Number: " + str(data[i]["train_num"]) )
          dispatcher.utter_message(data[i]["train_from"] + " to " + data[i]["train_to"])


            #print(response.text)
   
        
        #display(Image(response[0], height=550, width=520))
        #dispatcher.utter_message(response)
class ApiAction61(Action):
    def name(self):
        return "action_get_train_details_sm"

    def run(self, dispatcher, tracker, domain):
        url = "https://trains.p.rapidapi.com/"

        payload = "{\"search\":\"sampark kranti\"}"
        headers = {
        'x-rapidapi-host': "trains.p.rapidapi.com",
        'x-rapidapi-key': "cd60813deemsh9ba8b7139e55dd4p13b503jsn82c4f4eae495",
        'content-type': "application/json",
        'accept': "application/json"
        }

        response = requests.request("POST", url, data=payload, headers=headers)
        data = json.loads(response.text)
        #print(len(data))
        for i in range(0,len(data)):
          dispatcher.utter_message( "Train_Number: " + str(data[i]["train_num"]) )
          dispatcher.utter_message(data[i]["train_from"] + " to " + data[i]["train_to"])

        
        #display(Image(response[0], height=550, width=520))
        #dispatcher.utter_message(response)

class ApiAction7(Action):
    def name(self):
        return "action_give_news_in"

    def run(self, dispatcher, tracker, domain):
        url="https://newsapi.org/v2/top-headlines?"
        country ="in"
        api="1c641db096bd4d8d94c11cea964bb023"
        response=requests.get(url+"country="+country+"&apiKey="+api)

        #print(response.text)
        data=json.loads(response.text)
        
        #display(Image(response[0], height=550, width=520))
        dispatcher.utter_message(data["articles"][0]["title"])
class ApiAction71(Action):
    def name(self):
        return "action_give_news_us"

    def run(self, dispatcher, tracker, domain):
        url="https://newsapi.org/v2/top-headlines?"
        country ="us"
        api="1c641db096bd4d8d94c11cea964bb023"
        response=requests.get(url+"country="+country+"&apiKey="+api)

        #print(response.text)
        data=json.loads(response.text)
        
        #display(Image(response[0], height=550, width=520))
        dispatcher.utter_message(data["articles"][0]["title"])
class ApiAction8(Action):
    def name(self):
        return "get_movie_details1"

    def run(self, dispatcher, tracker, domain):
        url = "https://movie-database-imdb-alternative.p.rapidapi.com/"

        querystring = {"i":"tt4154796","r":"json"}

        headers = {
            'x-rapidapi-host': "movie-database-imdb-alternative.p.rapidapi.com",
            'x-rapidapi-key': "cd60813deemsh9ba8b7139e55dd4p13b503jsn82c4f4eae495"
                    }


        response = requests.request("GET", url, headers=headers, params=querystring)
        #print(response.text)
        data = json.loads(response.text)   
        
        #display(Image(response[0], height=550, width=520))
        dispatcher.utter_message(data["Actors"])
        dispatcher.utter_message(data["Ratings"][0]["Value"])

class ApiAction81(Action):
    def name(self):
        return "get_movie_details2"

    def run(self, dispatcher, tracker, domain):
        url = "https://movie-database-imdb-alternative.p.rapidapi.com/"

        querystring = {"i":"tt0452608","r":"json"}

        headers = {
            'x-rapidapi-host': "movie-database-imdb-alternative.p.rapidapi.com",
            'x-rapidapi-key': "cd60813deemsh9ba8b7139e55dd4p13b503jsn82c4f4eae495"
                    }


        response = requests.request("GET", url, headers=headers, params=querystring)
        #print(response.text)
        data = json.loads(response.text)   
        
        #display(Image(response[0], height=550, width=520))
        dispatcher.utter_message(data["Actors"])
        dispatcher.utter_message(data["Ratings"][0]["Value"])
