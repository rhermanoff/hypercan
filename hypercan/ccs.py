#!/usr/bin/python

import can
from can import Message
from device import device
from util import *
from apscheduler.schedulers.background import BackgroundScheduler

"""
This function handles any messages from the CCS
@param message
@return dictionary
"""
class ccs(device):
	"""
	Initializes all CCS attributes
	"""
	def __init__(self):
		# Daemonic scheduler for contactor requests
		self.scheduler = BackgroundScheduler(daemon=True)
		
		# CCS attributes
		self.voltage = None
		self.current = None
		self.hardware_failure = None
		self.temperature_of_charger = None
		self.input_voltage = None
		self.stating_state = None
		self.communication_state = None
	
	"""
	Handles message for CCS
	@param message  CAN message to parse
	@return hypercan_message
	"""
	def handle_message(self, message):
		# Decode voltage and current, {V/C} = {V/C}_high_bit * 10 + {V/C}_low_bit / 10.0
		voltage = message.data[0] * 10 + message.data[1] / 10.0
		current = message.data[2] * 10 + message.data[3] / 10.0

		# Status_bytes contains array of bit data for charger status, maybe a hack?
		status_bytes = format(message.data[4], 'b').zfill(5)
		
		hypercan_message = {
			'success':True,
			'device':'ccs',
			'type':None,
			'data':{
				'voltage':voltage,
				'current':current,
				'hardware_failure':bool_str(status_bytes[0]),
				'temperature_of_charger':bool_str(status_bytes[1]),
				'input_voltage':bool_str(status_bytes[2]),
				'stating_state':bool_str(status_bytes[3]),
				'communication_state':bool_str(status_bytes[4]),
			}
		}
		
		# Update object
		self.update_device(hypercan_message)
		
		return hypercan_message
		
	"""
	Internal function to command CCS to begin charging at a specified voltage and current
	@param driver  CAN driver to send message to
	@param voltage  Voltage to a precision of 0.1v	
	@param current  Current to a precision of 0.1A
	@param enable  Enable charge output
	"""
	def _send_charge_request(self, driver, voltage, current, enable):
	
		# Check for bad values
		if current < 0 or current > 12:
			raise Exception('Commanded current is invalid')
		if voltage < 0 or voltage > 650:
			raise Exception('Commanded voltage is invalid')
		
		# Construct and send message
		message = Message(
			extended_id = True,
			is_remote_frame = False,
			is_error_frame = False,
			arbitration_id = 0x1806E5F4,
			dlc = 8,
			data = bytearray(float_to_ccs_value(voltage) + float_to_ccs_value(current) + [0x00 if enable else 0x01, 0, 0, 0]),
		)
		
		driver.send_message(message)
		
	"""
	Instructs the charger to begin or end a charge cycle.
	Functionally tarts a scheduler to send a contactor request 
	every second
	
	PLEASE READ:
	THE CHARGER HAS THE ABILITY TO OUTPUT EXTREMELY HIGH VOLTAGES AND
	HIGH CURRENTS.  IF YOU MISUSE THE CHARGER AND COMMAND IT WRONG YOU
	COULD SERIOUSLY INJURE OR KILL YOURSELF.  THE BATTERY IS ALSO EXTREMELY
	SENSITIVE TO CHARGING AND CARE SHOULD BE TAKEN TO ENSURE THAT THE BMS
	CAN SHUT OFF THE CHARGER WHEN HLIM IS REACHED.  FAILURE TO DO SO WILL
	RESULT IN THE BATTERY BEING OVERCHARGED AND EXPLODING.
	
	@param driver  CAN driver to send message to
	@param voltage  Voltage to a precision of 0.1v	
	@param current  Current to a precision of 0.1A
	@param enable  Enable charge output
	"""
	def set_charge(self, driver, voltage, current, enable):
		# Register job with scheduler and begin
		self.scheduler.add_job(self._send_charge_request,'interval',args=[driver, voltage, current, enable], seconds=1)
		self.scheduler.start()