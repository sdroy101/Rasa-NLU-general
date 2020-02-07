from __future__ import absolute_import
from __future__ import division
from __future__ import unicode_literals

from rasa_core.domain import Domain
from rasa_core.trackers import EventVerbosity


import requests
import json

from rasa_core_sdk import Action
from rasa_core_sdk.events import SlotSet
from rasa_core_sdk.events import UserUtteranceReverted
from rasa_core_sdk.events import AllSlotsReset
from rasa_core_sdk.events import Restarted
class SaveOrigin(Action):
	def name(self):
		return 'action_save_origin'
		
	def run(self, dispatcher, tracker, domain):
		origin = next(tracker.get_latest_entity_values("location"), None)
		return [SlotSet('from',origin)]

class SaveDestination(Action):
	def name(self):
		return 'action_save_destination'
		
	def run(self, dispatcher, tracker, domain):
		dest = next(tracker.get_latest_entity_values("location"), None)
		return [SlotSet('to',dest)]
class SaveDate(Action):
	def name(self):
		return 'action_save_date'
		
	def run(self, dispatcher, tracker, domain):
		bd = next(tracker.get_latest_entity_values("date"), None)
		return [SlotSet('date',bd)]

class getFlightStatus(Action):
	def name(self):
		return 'action_get_flight'
		def run(self, dispatcher, tracker, domain):
		orig=tracker.get_slot('from')
		dest=tracker.get_slot('to')
		dat=tracker.get_slot('date')
		base_url = "https://skyscanner-skyscanner-flight-search-v1.p.rapidapi.com/apiservices/browseroutes/v1.0/IN/INR/en-IN/{}/{}/{}"
		headers = {
            'x-rapidapi-host': "skyscanner-skyscanner-flight-search-v1.p.rapidapi.com",
	        'x-rapidapi-key': "00471bbb4emsh5536b2c4ef12ee1p10420bjsn9220608af04d",
	        'content-type': "application/x-www-form-urlencoded"
                    }
		page=request.request(base_url.format(orig,dest,dat), headers )
		data = json.loads(page.text)
		for i in range(0,len(data)):
			dispatcher.utter_message( "Fight ID: " + str(data[i]["CarrierId"]) )
			dispatcher.utter_message("Airlines name:"+ str(data[i]["Name"]))
			dispatcher.utter_message("Min fare:"+ str(data[i]["MinPrice"]))
		
