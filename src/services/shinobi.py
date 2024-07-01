import json
import logging
import uuid
from collections import defaultdict
from typing import Optional, Dict, List

import requests
from aiohttp import ClientSession

from src.api.schema import OrganizationCameraSchema
from src.config import settings
from src.schema import NewCameraRequestSchema, VideoSchema

logger = logging.getLogger("uvicorn")


class Shinobi:
    def __init__(self, email: str, password: str, auth_key: str):
        self.email = email
        self.password = password

        self.auth_key = auth_key
        self.group_key = None
        self.base_url = settings.SHINOBI_URL

        self.recorded_monitor_register: dict[str, int] = defaultdict(int)

    def register_monitors(self, monitors: list[OrganizationCameraSchema]):
        for monitor in monitors:
            self.recorded_monitor_register[monitor.monitor_id] = 0

    async def start_monitor_recording(self, monitor_id: str) -> bool:
        """
        Start monitor recording
        :param monitor_id: id of the monitor
        :return: True if the monitor recording was started, False otherwise
        """

        monitor_recording_events = self.recorded_monitor_register.get(monitor_id, 0)
        if monitor_recording_events > 0:
            self.recorded_monitor_register[monitor_id] += 1
            return True

        url = f"{self.base_url}/{self.auth_key}/monitor/{self.group_key}/{monitor_id}/record"
        response = await self._send_request(url)
        self.recorded_monitor_register[monitor_id] += 1
        return response is not None

    async def stop_monitor_recording(self, monitor_id: str) -> bool:
        """
        Stop monitor recording
        :param monitor_id: id of the monitor
        :return: True if the monitor recording was stopped, False otherwise
        """
        monitor_recording_events = self.recorded_monitor_register.get(monitor_id, 0)
        monitor_recording_events -= 1
        if monitor_recording_events > 0:
            return True

        url = f"{self.base_url}/{self.auth_key}/monitor/{self.group_key}/{monitor_id}/start"
        response = await self._send_request(url)
        self.recorded_monitor_register[monitor_id] -= (
            1 if monitor_recording_events > 0 else 0
        )
        return response is not None

    async def manage_monitor(
        self, payload: NewCameraRequestSchema, monitor_id: str = None
    ) -> Optional[str]:
        """
        Create/update a new monitor
        :param payload: monitor data
        :param monitor_id: monitor id only for update process
        :return: monitor id
        """

        self.set_credentials()

        if not monitor_id:
            monitor_id = str(uuid.uuid4()).replace("-", "")
        data = {
            "mode": "start",
            "mid": monitor_id,
            "name": payload.name,
            "type": "h264",
            "host": payload.host,
            "port": payload.port,
            "path": payload.path,
            "protocol": "rtsp",
            "height": "480",
            "width": "640",
            "ext": "mp4",
            "preset_record": "",
            "fps": "1",
            "details": {
                "max_keep_days": "",
                "notes": "",
                "dir": "",
                "rtmp_key": "",
                "auto_host_enable": "1",
                "auto_host": f"rtsp://{payload.username}:{payload.password}@{payload.host}:{payload.port}{payload.path}",
                "rtsp_transport": "tcp",
                "muser": payload.username,
                "mpass": payload.password,
                "onvif_port": payload.port,
                "stream_type": "hls",
                "port_force": "0",
                "fatal_max": "0",
                "skip_ping": None,
                "is_onvif": None,
                "primary_input": None,
                "aduration": "1000000",
                "probesize": "1000000",
                "stream_loop": "0",
                "sfps": "",
                "accelerator": "0",
                "hwaccel": "auto",
                "hwaccel_vcodec": "",
                "hwaccel_device": "",
                "use_coprocessor": None,
                "stream_flv_type": "ws",
                "stream_flv_maxLatency": "",
                "stream_mjpeg_clients": "",
                "stream_vcodec": "copy",
                "stream_acodec": "no",
                "hls_time": "2",
                "hls_list_size": "3",
                "preset_stream": "ultrafast",
                "signal_check": "10",
                "signal_check_log": "0",
                "stream_quality": "15",
                "stream_fps": "2",
                "stream_scale_x": "",
                "stream_scale_y": "",
                "rotate_stream": "no",
                "svf": "",
                "tv_channel": "0",
                "tv_channel_id": "",
                "tv_channel_group_title": "",
                "stream_timestamp": "0",
                "stream_timestamp_font": "",
                "stream_timestamp_font_size": "",
                "stream_timestamp_color": "",
                "stream_timestamp_box_color": "",
                "stream_timestamp_x": "",
                "stream_timestamp_y": "",
                "stream_watermark": "0",
                "stream_watermark_location": "",
                "stream_watermark_position": "tr",
                "snap": "1",
                "snap_fps": "",
                "snap_scale_x": "640",
                "snap_scale_y": "480",
                "snap_vf": "",
                "vcodec": "copy",
                "crf": "1",
                "acodec": "no",
                "record_scale_y": "",
                "record_scale_x": "",
                "cutoff": "15",
                "rotate_record": "no",
                "vf": "",
                "timestamp": "0",
                "timestamp_font": "",
                "timestamp_font_size": "10",
                "timestamp_color": "white",
                "timestamp_box_color": "0x00000000@1",
                "timestamp_x": "(w-tw)/2",
                "timestamp_y": "0",
                "watermark": "0",
                "watermark_location": "",
                "watermark_position": "tr",
                "record_timelapse": None,
                "record_timelapse_mp4": None,
                "record_timelapse_fps": None,
                "record_timelapse_scale_x": "",
                "record_timelapse_scale_y": "",
                "record_timelapse_vf": "",
                "record_timelapse_watermark": None,
                "record_timelapse_watermark_location": "",
                "record_timelapse_watermark_position": None,
                "cust_input": "",
                "cust_stream": "",
                "cust_snap": "",
                "cust_record": "",
                "cust_detect": "",
                "cust_sip_record": "",
                "custom_output": "",
                "detector": "0",
                "detector_http_api": None,
                "detector_send_frames": "1",
                "detector_lock_timeout": "",
                "detector_save": "0",
                "detector_fps": "",
                "detector_scale_x": "640",
                "detector_scale_y": "480",
                "detector_record_method": "sip",
                "detector_trigger": "1",
                "detector_trigger_record_fps": "",
                "detector_timeout": "10",
                "detector_send_video_length": "",
                "watchdog_reset": "0",
                "detector_delete_motionless_videos": "0",
                "det_multi_trig": None,
                "group_detector_multi": "",
                "detector_webhook": "0",
                "detector_webhook_url": "",
                "detector_webhook_method": None,
                "detector_command_enable": "0",
                "detector_command": "",
                "detector_command_timeout": "",
                "detector_mail": "0",
                "detector_mail_timeout": "",
                "detector_discordbot": None,
                "detector_discordbot_send_video": None,
                "detector_discordbot_timeout": "",
                "use_detector_filters": None,
                "use_detector_filters_object": None,
                "cords": "[]",
                "detector_filters": "",
                "detector_pam": "1",
                "detector_show_matrix": None,
                "detector_sensitivity": "",
                "detector_max_sensitivity": "",
                "detector_threshold": "1",
                "detector_color_threshold": "",
                "detector_frame": "0",
                "detector_noise_filter": None,
                "detector_noise_filter_range": "",
                "detector_notrigger": "0",
                "detector_notrigger_mail": "0",
                "detector_notrigger_timeout": "",
                "detector_audio": None,
                "detector_audio_min_db": "",
                "detector_audio_max_db": "",
                "detector_use_detect_object": "0",
                "detector_send_frames_object": None,
                "detector_obj_region": None,
                "detector_use_motion": "1",
                "detector_fps_object": "",
                "detector_scale_x_object": "",
                "detector_scale_y_object": "",
                "detector_lisence_plate": "0",
                "detector_lisence_plate_country": "us",
                "detector_buffer_vcodec": "auto",
                "detector_buffer_acodec": None,
                "detector_buffer_fps": "",
                "detector_buffer_hls_time": "",
                "detector_buffer_hls_list_size": "",
                "detector_buffer_start_number": "",
                "detector_buffer_live_start_index": "",
                "control": "0",
                "control_base_url": "",
                "control_url_method": None,
                "control_digest_auth": None,
                "control_stop": "0",
                "control_url_stop_timeout": "",
                "control_url_center": "",
                "control_url_left": "",
                "control_url_left_stop": "",
                "control_url_right": "",
                "control_url_right_stop": "",
                "control_url_up": "",
                "control_url_up_stop": "",
                "control_url_down": "",
                "control_url_down_stop": "",
                "control_url_enable_nv": "",
                "control_url_disable_nv": "",
                "control_url_zoom_out": "",
                "control_url_zoom_out_stop": "",
                "control_url_zoom_in": "",
                "control_url_zoom_in_stop": "",
                "groups": [],
                "loglevel": "warning",
                "sqllog": "0",
                "detector_cascades": "",
                "stream_channels": "",
                "input_maps": "",
                "input_map_choices": "",
            },
            "shto": [],
            "shfr": [],
        }

        url = f"{self.base_url}/{self.auth_key}/configureMonitor/{self.group_key}/{monitor_id}"

        # Sending the POST request
        response = await self._send_post_request(url, data)
        logger.info(response)
        return monitor_id

    async def delete_monitor(self, monitor_id: str):
        self.set_credentials()
        url = f"{self.base_url}/{self.auth_key}/configureMonitor/{self.group_key}/{monitor_id}/delete"

        # Sending the POST request
        response = await self._send_post_request(url)
        logger.info(response)
        return monitor_id

    async def create_snapshot(self, monitor_id: str) -> Optional[bytes]:
        self.set_credentials()
        url = (
            f"{self.base_url}/{self.auth_key}/jpeg/{self.group_key}/{monitor_id}/s.jpg"
        )
        response = await self._send_request(url)

        logger.info(response)
        return response

    async def video(self) -> List[VideoSchema]:
        self.set_credentials()

        url = f"{self.base_url}/{self.auth_key}/videos/{self.group_key}"
        response = await self._send_request(url)
        if not response:
            return []
        return [
            VideoSchema(
                monitor_id=item.get("mid"),
                filename=item.get("filename"),
                start=item.get("time"),
                end=item.get("end"),
                video_url=item.get("href"),
            )
            for item in response.get("videos", [])
        ]

    async def monitor_video(
        self, monitor_id: str, start: str = None, end: str = None
    ) -> List[VideoSchema]:
        self.set_credentials()

        url = f"{self.base_url}/{self.auth_key}/videos/{self.group_key}/{monitor_id}"
        query_params = {}
        if start:
            query_params["start"] = start
        if end:
            query_params["end"] = end

        response = await self._send_request(url, params=query_params)

        logger.info(response)
        if not response:
            return []

        return [
            VideoSchema(
                monitor_id=item.get("mid"),
                filename=item.get("filename"),
                start=item.get("time"),
                end=item.get("end"),
                video_url=item.get("href"),
            )
            for item in response.get("videos", [])
        ]

    async def delete_video(self, monitor_id: str, video_filename: str):
        self.set_credentials()

        url = f"{self.base_url}/{self.auth_key}/videos/{self.group_key}/{monitor_id}/{video_filename}/delete"
        response = await self._send_request(url)

        logger.info(response)
        return None

    def set_credentials(self):
        url = f"{self.base_url}/{self.auth_key}/?json=true"

        payload = json.dumps(
            {
                "mail": self.email,
                "pass": self.password,
            }
        )
        headers = {"Content-Type": "application/json"}

        response = requests.request("POST", url, headers=headers, data=payload)
        if response.status_code != 200:
            logger.error(f"cant send auth request to shinobi: {response.content}")
            return

        data = response.json()
        self.auth_key = data["$user"]["auth_token"]
        self.group_key = data["$user"]["ke"]

    async def _send_request(self, url: str, params: Dict = None) -> Optional[Dict]:
        async with ClientSession() as session:
            async with session.get(url, params=params) as response:
                if response.status == 200:
                    response_body = await response.json()
                    return response_body
                else:
                    logger.error(f"cant send request to shinobi: {response.content}")
                return None

    async def _send_post_request(
        self, url: str, payload: Dict = None
    ) -> Optional[Dict]:
        async with ClientSession() as session:
            async with session.post(url, data=payload) as response:
                if response.status == 200:
                    response_body = await response.json()
                    return response_body
                else:
                    logger.error(f"cant send request to shinobi: {response.content}")
                return None
