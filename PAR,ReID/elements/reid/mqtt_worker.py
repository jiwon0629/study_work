import argparse
import logging
import signal
import sys
import threading
import time

from .worker.publisher import MQTTPublisher, parse_broker_url


class FixedTopicPublisher:
    def __init__(
        self,
        *,
        broker_url: str,
        topic: str,
        qos: int,
        client_id: str,
        username: str,
        password: str,
        queue_size: int,
        publish_timeout_ms: int,
        keepalive: int,
    ) -> None:
        if qos not in {0, 1, 2}:
            raise ValueError("qos must be 0, 1, or 2")
        if not topic:
            raise ValueError("topic must not be empty")
        parse_broker_url(broker_url)

        self.topic = topic
        self.publisher = MQTTPublisher(
            broker_url=broker_url,
            qos=qos,
            client_id=client_id,
            username=username,
            password=password,
            queue_size=queue_size,
            publish_timeout_ms=publish_timeout_ms,
            keepalive=keepalive,
            max_retries=0,
        )

    @property
    def stop_event(self):
        return self.publisher.stop_event

    @property
    def published_count(self) -> int:
        return self.publisher.published_count

    @property
    def dropped_count(self) -> int:
        return self.publisher.dropped_count

    def enqueue(self, payload: str) -> None:
        ok = self.publisher.enqueue(self.topic, payload)
        if not ok:
            raise RuntimeError("publish queue is full")

    def close(self) -> None:
        self.publisher.close()


def read_stdin(publisher: FixedTopicPublisher) -> None:
    for line in sys.stdin:
        if publisher.stop_event.is_set():
            break
        payload = line.strip()
        if not payload:
            continue
        publisher.enqueue(payload)
    publisher.stop_event.set()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="MQTT publisher for async object detection events")
    parser.add_argument("--broker", required=True, help="MQTT broker URL")
    parser.add_argument("--topic", required=True, help="MQTT topic to publish")
    parser.add_argument("--qos", type=int, required=True, help="MQTT QoS level")
    parser.add_argument("--queue-size", type=int, required=True, help="Maximum buffered events")
    parser.add_argument("--publish-timeout-ms", type=int, required=True, help="Publish timeout in milliseconds")
    parser.add_argument("--keepalive", type=int, required=True, help="MQTT keepalive in seconds")
    parser.add_argument("--client-id", required=True, help="MQTT client id")
    parser.add_argument("--username", required=True, help="MQTT username")
    parser.add_argument("--password", required=True, help="MQTT password")
    return parser.parse_args()


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    args = parse_args()

    try:
        publisher = FixedTopicPublisher(
            broker_url=args.broker,
            topic=args.topic,
            qos=args.qos,
            client_id=args.client_id,
            username=args.username,
            password=args.password,
            queue_size=args.queue_size,
            publish_timeout_ms=args.publish_timeout_ms,
            keepalive=args.keepalive,
        )
    except Exception as exc:
        logging.error("Failed to initialize MQTT publisher: %s", exc)
        return 1

    def handle_signal(signum, frame):
        logging.info("Signal %s received, shutting down", signum)
        publisher.stop_event.set()

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    reader_thread = threading.Thread(target=read_stdin, args=(publisher,), name="stdin-reader", daemon=True)
    reader_thread.start()

    while not publisher.stop_event.is_set():
        time.sleep(0.5)

    reader_thread.join(timeout=1.0)
    publisher.close()
    logging.info("MQTT publisher stopped. published=%d dropped=%d", publisher.published_count, publisher.dropped_count)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
