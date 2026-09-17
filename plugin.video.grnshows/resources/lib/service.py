# -*- coding: utf-8 -*-
from xbmc import Monitor
import os
import json
import inspect
from time import time
from threading import Thread
from caches.settings_cache import get_setting, set_setting, sync_settings
from modules import kodi_utils

pause_services_prop = 'grnshows.pause_services'
firstrun_update_prop = 'grnshows.firstrun_update'
current_skin_prop = 'grnshows.current_skin'
trakt_service_string = 'TraktMonitor Service Update %s - %s'
trakt_success_line_dict = {'success': 'Trakt Update Performed', 'no account': '(Unauthorized) Trakt Update Performed'}
update_string = 'Next Update in %s minutes...'

class SetAddonConstants:
	def run(self):
		kodi_utils.logger('GRN Shows', 'SetAddonConstants Service Starting')
		import random
		addon_items = [
			('grnshows.playback_key', str(random.randint(1000, 10000))),
			('grnshows.addon_version', kodi_utils.addon_info('version')),
			('grnshows.addon_path', kodi_utils.addon_info('path')),
			('grnshows.addon_profile', kodi_utils.translate_path(kodi_utils.addon_info('profile'))),
			('grnshows.addon_icon', kodi_utils.translate_path(kodi_utils.addon_info('icon'))),
			('grnshows.addon_icon_mini', os.path.join(kodi_utils.addon_info('path'), 'resources', 'media', 'addon_icons', 'minis',
			os.path.basename(kodi_utils.translate_path(kodi_utils.addon_info('icon'))))),
			('grnshows.addon_fanart', kodi_utils.addon_fanart())
					]
		for item in addon_items: kodi_utils.set_property(*item)
		return kodi_utils.logger('GRN Shows', 'SetAddonConstants Service Finished')

class DatabaseMaintenance:
	def run(self):
		kodi_utils.logger('GRN Shows', 'DatabaseMaintenance Service Starting')
		from caches.base_cache import check_databases_integrity
		check_databases_integrity(silent=True)
		return kodi_utils.logger('GRN Shows', 'DatabaseMaintenance Service Finished')

class SyncSettings:
	def run(self):
		kodi_utils.logger('GRN Shows', 'SyncSettings Service Starting')
		sync_settings()
		return kodi_utils.logger('GRN Shows', 'SyncSettings Service Finished')

class OnUpdateChanges:
	def run(self):
		kodi_utils.logger('GRN Shows', 'OnUpdateChanges Service Starting')
		try:
			for method in list(filter(lambda x: x[0] != 'run', inspect.getmembers(OnUpdateChanges, predicate=inspect.isfunction))):
				if not get_setting('grnshows.updatechecks.%s' % method[0], 'false') == 'true':
					method[1](self)
					set_setting('updatechecks.%s' % method[0], 'true')
		except: pass
		return kodi_utils.logger('GRN Shows', 'OnUpdateChanges Service Finished')

	def refresh_addon_keys(self):
		# For update 2.2.01 - 03
		from hashlib import sha256
		from caches.trakt_cache import clear_all_trakt_cache_data
		from caches.tmdb_lists import tmdb_lists_cache
		from caches.settings_cache import restore_setting_default
		show_dialog = False
		tmdb_default_hashes = ('dd56245dc027bb3106ca44cf449f036950fae91bd16d01c5ca66da3c5990fc39',
								'09e9d6a99794253af2540b2918060e79f71bc133047970892e02ba2fa20686de')
		trakt_default_hashes = ('36d2036fe8244425be55b91b3fde71c52dea1dd9772624957f9d3e76046cd1db',
								'd63260fe6d210ce0ac387fae20c1f5d381197c77f750513f98ad360200b3d20a')
		if sha256(get_setting('grnshows.tmdb_api', '').encode('utf-8')).hexdigest() in tmdb_default_hashes:
			restore_setting_default({'silent': 'true', 'setting_id': 'tmdb_api'})
			set_setting('tmdb.token', 'empty_setting')
			set_setting('tmdb.account_id', 'empty_setting')
			set_setting('tmdb.username', 'empty_setting')
			set_setting('tmdb.session_id', 'empty_setting')
			set_setting('tmdb.account_session_id', 'empty_setting')
			tmdb_lists_cache.clear_all()
			show_dialog = True
		if sha256(get_setting('grnshows.trakt.client', '').encode('utf-8')).hexdigest() in trakt_default_hashes:
			restore_setting_default({'silent': 'true', 'setting_id': 'trakt.client'})
			set_setting('trakt.user', 'empty_setting')
			set_setting('trakt.expires', '0')
			set_setting('trakt.token', '0')
			set_setting('trakt.refresh', '0')
			set_setting('trakt.next_daily_clear', '0')
			set_setting('watched_indicators', '0')
			clear_all_trakt_cache_data(silent=True, refresh=False)
			show_dialog = True
		if show_dialog:
			text = 'The original developer of GRN Shows has revoked all keys (Trakt, TMDb) that have been used up until now '\
			'within this addon, with permission, due to security concerns.'
			kodi_utils.ok_dialog(heading='Addon Credentials Reset', text=text)
			text = 'This unfortunately means you will need to re-authenticate your Trakt & TMDb accounts through GRN Shows AM  if you are currently using them. ' \
			'My apologies, but with the previous keys being revoked, this is necessary.'
			kodi_utils.ok_dialog(heading='Addon Credentials Reset', text=text)

class CustomWindowsPrepare:
	def run(self):
		kodi_utils.logger('GRN Shows', 'CustomWindowsPrepare Service Starting')
		from windows.base_window import FontUtils, ExtrasUtils
		monitor, player = kodi_utils.kodi_monitor(), kodi_utils.kodi_player()
		wait_for_abort, is_playing = monitor.waitForAbort, player.isPlayingVideo
		kodi_utils.clear_property(current_skin_prop)
		ExtrasUtils().run()
		font_utils = FontUtils()
		while not monitor.abortRequested():
			font_utils.execute_custom_fonts()
			wait_for_abort(20)
		try: del monitor
		except: pass
		try: del player
		except: pass
		return kodi_utils.logger('GRN Shows', 'CustomWindowsPrepare Service Finished')

class TraktMonitor:
	def run(self):
		kodi_utils.logger('GRN Shows', 'TraktMonitor Service Starting')
		from apis.trakt_api import trakt_sync_activities
		from modules.settings import trakt_user_active, trakt_sync_interval
		monitor, player = kodi_utils.kodi_monitor(), kodi_utils.kodi_player()
		wait_for_abort, is_playing = monitor.waitForAbort, player.isPlayingVideo
		while not monitor.abortRequested():
			while is_playing() or kodi_utils.get_property(pause_services_prop) == 'true': wait_for_abort(10)
			wait_time = 1800
			try:
				sync_interval, wait_time = trakt_sync_interval()
				next_update_string = update_string % sync_interval
				if trakt_user_active: status = trakt_sync_activities()
				else: status = 'no_auth'
				if status == 'failed': kodi_utils.logger('GRN Shows', trakt_service_string % ('Failed. Error from Trakt', next_update_string))
				elif status == 'no_auth': kodi_utils.logger('GRN Shows', trakt_service_string % ('Not Run. No Current Trakt Account', next_update_string))
				else:
					if status in ('success', 'no account'):
						kodi_utils.logger('GRN Shows', trakt_service_string % ('Success. %s' % trakt_success_line_dict[status], next_update_string))
					else:
						kodi_utils.logger('GRN Shows', trakt_service_string % ('Success. No Changes Needed', next_update_string))# 'not needed'
					if status == 'success' and get_setting('grnshows.trakt.refresh_widgets', 'false') == 'true':
						kodi_utils.run_plugin({'mode': 'kodi_refresh'})
			except Exception as e: kodi_utils.logger('GRN Shows', trakt_service_string % ('Failed', 'The following Error Occured: %s' % str(e)))
			wait_for_abort(wait_time)
		try: del monitor
		except: pass
		try: del player
		except: pass
		return kodi_utils.logger('GRN Shows', 'TraktMonitor Service Finished')

class UpdateCheck:
	def run(self):
		if kodi_utils.get_property(firstrun_update_prop) == 'true': return
		kodi_utils.logger('GRN Shows', 'UpdateCheck Service Starting')
		from modules.updater import update_check
		from modules.settings import update_action, update_delay
		end_pause = time() + update_delay()
		monitor, player = kodi_utils.kodi_monitor(), kodi_utils.kodi_player()
		wait_for_abort, is_playing = monitor.waitForAbort, player.isPlayingVideo
		while not monitor.abortRequested():
			while time() < end_pause: wait_for_abort(1)
			while kodi_utils.get_property(pause_services_prop) == 'true' or is_playing(): wait_for_abort(1)
			update_check(update_action())
			break
		kodi_utils.set_property(firstrun_update_prop, 'true')
		try: del monitor
		except: pass
		try: del player
		except: pass
		return kodi_utils.logger('GRN Shows', 'UpdateCheck Service Finished')

class WidgetRefresher:
	def run(self):
		kodi_utils.logger('GRN Shows', 'WidgetRefresher Service Starting')
		from time import time
		monitor, player = kodi_utils.kodi_monitor(), kodi_utils.kodi_player()
		wait_for_abort, self.is_playing = monitor.waitForAbort, player.isPlayingVideo
		wait_for_abort(10)
		self.set_next_refresh(time())
		while not monitor.abortRequested():
			try:
				wait_for_abort(10)
				offset = int(get_setting('grnshows.widget_refresh_timer', '60'))
				if offset != self.offset:
					self.set_next_refresh(time())
					continue
				if self.condition_check(): continue
				if self.next_refresh < time():
					kodi_utils.logger('GRN Shows', 'WidgetRefresher Service - Widgets Refreshed')
					kodi_utils.refresh_widgets()
					self.set_next_refresh(time())
			except: pass
		try: del monitor
		except: pass
		try: del player
		except: pass
		return kodi_utils.logger('GRN Shows', 'WidgetRefresher Service Finished')

	def condition_check(self):
		if not self.external(): return True

		if self.next_refresh == None or self.is_playing() or kodi_utils.get_property(pause_services_prop) == 'true': return True
		if kodi_utils.get_property('grnshows.window_loaded') == 'true': return True 
		try:
			window_stack = json.loads(kodi_utils.get_property('grnshows.window_stack'))
			if window_stack or window_stack == []: return True
		except: pass
		return False

	def set_next_refresh(self, _time):
		self.offset = int(get_setting('grnshows.widget_refresh_timer', '60'))
		if self.offset: self.next_refresh = _time + (self.offset*60)
		else: self.next_refresh = None

	def external(self):
		return 'plugin' not in kodi_utils.get_infolabel('Container.PluginName')

class AutoStart:
	def run(self):
		kodi_utils.logger('GRN Shows', 'AutoStart Service Starting')
		from modules.settings import auto_start_grnshows
		if auto_start_grnshows(): kodi_utils.run_addon()
		return kodi_utils.logger('GRN Shows', 'AutoStart Service Finished')

class AddonXMLCheck:
	def run(self):
		kodi_utils.logger('GRN Shows', 'AddonXMLCheck Service Starting')
		from xml.dom.minidom import parse as mdParse
		self.addon_xml = kodi_utils.translate_path('special://home/addons/plugin.video.grnshows/addon.xml')
		self.root = mdParse(self.addon_xml)
		self.change_list = []
		self.check_property('reuse_language_invoker', 'reuselanguageinvoker')
		self.check_property('addon_icon_choice', 'icon')
		self.change_xml_file()
		return kodi_utils.logger('GRN Shows', 'AddonXMLCheck Service Finished')

	def check_property(self, setting, tag_name):
		current_addon_setting = get_setting('grnshows.%s' % setting, None)
		if current_addon_setting is None: return
		tag_instance = self.root.getElementsByTagName(tag_name)[0].firstChild
		current_property = tag_instance.data
		if current_property != current_addon_setting:
			tag_instance.data = current_addon_setting
			self.change_list.append(tag_name)

	def change_xml_file(self):
		if not self.change_list: return
		if 'icon' in self.change_list: self.reassign_addon_icon()
		kodi_utils.notification('Refreshing Addon XML. Restarting Addons')
		new_xml = str(self.root.toxml()).replace('<?xml version="1.0" ?>', '')
		with open(self.addon_xml, 'w') as f: f.write(new_xml)
		kodi_utils.logger('GRN Shows', 'AddonXMLCheck Service - Change Detected. Restarting Addons')
		kodi_utils.execute_builtin('ActivateWindow(Home)', True)
		kodi_utils.update_local_addons()
		kodi_utils.disable_enable_addon()

	def reassign_addon_icon(self):
		from indexers.dialogs import addon_icon_choice
		addon_icon_choice({'set_icon': get_setting('addon_icon_choice_name', 'grnshows_icon_01.png')})

class GRNShowsMonitor(Monitor):
	def __init__ (self):
		Monitor.__init__(self)
		self.startServices()

	def startServices(self):
		try: SetAddonConstants().run()
		except Exception as e: logger('SetAddonConstants', str(e))
		try: DatabaseMaintenance().run()
		except Exception as e: logger('DatabaseMaintenance', str(e))
		try: SyncSettings().run()
		except Exception as e: logger('SyncSettings', str(e))
		try: OnUpdateChanges().run()
		except Exception as e: logger('OnUpdateChanges', str(e))
		try: AddonXMLCheck().run()
		except Exception as e: logger('AddonXMLCheck', str(e))
		Thread(target=CustomWindowsPrepare().run).start()
		Thread(target=TraktMonitor().run).start()
		Thread(target=UpdateCheck().run).start()
		Thread(target=WidgetRefresher().run).start()
		try: AutoStart().run()
		except Exception as e: logger('AutoStart', str(e))

	def onNotification(self, sender, method, data):
		if method in ('GUI.OnScreensaverActivated', 'System.OnSleep'):
			kodi_utils.set_property(pause_services_prop, 'true')
			kodi_utils.logger('OnNotificationActions', 'PAUSING GRN Shows Services Due to Device Sleep')
		elif method in ('GUI.OnScreensaverDeactivated', 'System.OnWake'):
			kodi_utils.clear_property(pause_services_prop)
			kodi_utils.logger('OnNotificationActions', 'UNPAUSING GRN Shows Services Due to Device Awake')

kodi_utils.logger('GRN Shows', 'Main Monitor Service Starting')
GRNShowsMonitor().waitForAbort()
kodi_utils.logger('GRN Shows', 'Main Monitor Service Finished')
