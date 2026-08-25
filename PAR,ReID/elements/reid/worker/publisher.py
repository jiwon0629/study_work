import logging
import queue
import threading
import time
from urllib.parse import urlparse

import paho.mqtt.client as mqtt


def parse_broker_url(raw_url: str) -> tuple[str, int]:
    if not raw_url:
        raise ValueError("broker URL is empty")

    if "://" in raw_url:
        parsed = urlparse(raw_url)
        scheme = (parsed.scheme or "").lower()
        if scheme not in {"mqtt", "tcp"}:
            raise ValueError(f"unsupported broker scheme: {scheme}")
        if not parsed.hostname:
            raise ValueError("broker hostname is missing")
        if parsed.port is None:
            raise ValueError("broker port is required")
        return parsed.hostname, parsed.port

    if raw_url.startswith("["):
        end = raw_url.find("]")
        if end == -1:
            raise ValueError("invalid IPv6 broker format")
        host = raw_url[1:end]
        rest = raw_url[end + 1 :]
        if not rest.startswith(":"):
            raise ValueError("broker port is required")
        return host, int(rest[1:])

    if ":" in raw_url:
        host, port = raw_url.rsplit(":", 1)
        if not host:
            raise ValueError("broker hostname is missing")
        return host, int(port)

    raise ValueError("broker port is required")


class MQTTPublisher:
    def __init__(
        self,
        broker_url: str,
        qos: int,
        client_id: str,
        username: str,
        password: str,
        queue_size: int,
        publish_timeout_ms: int,
        keepalive: int,
        max_retries: int,
    ) -> None:
        if queue_size <= 0:
            raise ValueError("queue_size must be greater than 0")
        if publish_timeout_ms <= 0:
            raise ValueError("publish_timeout_ms must be greater than 0")
        if keepalive <= 0:
            raise ValueError("keepalive must be greater than 0")

        self.qos = qos
        self.queue: queue.Queue[tuple[str, str]] = queue.Queue(maxsize=queue_size)
        self.publish_timeout = publish_timeout_ms / 1000.0
        self.connected = threading.Event()
        self.stop_event = threading.Event()
        self.dropped_count = 0
        self.published_count = 0
        self.max_retries = max_retries

        host, port = parse_broker_url(broker_url)

        self.client = mqtt.Client(client_id=client_id)
        if username or password:
            self.client.username_pw_set(username, password)
        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect
        self.client.reconnect_delay_set(min_delay=1, max_delay=30)
        result = self.client.connect(host, port, keepalive=keepalive)
        if result != mqtt.MQTT_ERR_SUCCESS:
            raise RuntimeError(f"MQTT connect failed with rc={result}")

        self.client.loop_start()

        self.publisher_thread = threading.Thread(target=self._publish_loop, name="mqtt-publisher", daemon=True)
        self.publisher_thread.start()

    def _on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            self.connected.set()
            logging.info("MQTT connected")
        else:
            logging.error("MQTT connect failed with rc=%s", rc)

    def _on_disconnect(self, client, userdata, rc):
        self.connected.clear()
        if not self.stop_event.is_set():
            logging.warning("MQTT disconnected with rc=%s", rc)

    def enqueue(self, topic: str, payload: str) -> bool:
        try:
            self.queue.put_nowait((topic, payload))
            return True
        except queue.Full:
            self.dropped_count += 1
            return False

    def _publish_loop(self) -> None:
        while not self.stop_event.is_set():
            try:
                topic, payload = self.queue.get(timeout=0.5)
            except queue.Empty:
                continue

            attempts = 0
            published = False
            while attempts <= self.max_retries and not self.stop_event.is_set():
                attempts += 1
                try:
                    self._publish_once(topic, payload)
                    self.published_count += 1
                    published = True
                    break
                except Exception as exc:
                    logging.error("Publish failed (%d/%d): %s", attempts, self.max_retries, exc)
                    time.sleep(0.2 * attempts)

            if not published:
                self.dropped_count += 1

            self.queue.task_done()

    def _publish_once(self, topic: str, payload: str) -> None:
        if not self.connected.is_set():
            raise RuntimeError("MQTT not connected")

        info = self.client.publish(topic, payload, qos=self.qos)
        if info.rc != mqtt.MQTT_ERR_SUCCESS:
            raise RuntimeError(f"MQTT publish failed with rc={info.rc}")

        if self.qos > 0:
            if not info.wait_for_publish(timeout=self.publish_timeout):
                raise RuntimeError("MQTT publish timed out")

    def close(self) -> None:
        self.stop_event.set()
        self.publisher_thread.join(timeout=2)
        self.client.loop_stop()
        self.client.disconnect()
