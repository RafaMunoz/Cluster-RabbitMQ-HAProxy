#!/usr/bin/python
# -*- coding: utf-8 -*-

import pika

params = pika.URLParameters('amqp://admin:admin@192.168.1.230')
connection = pika.BlockingConnection(params)
channel = connection.channel()
channel.queue_declare(queue='debug')
channel.basic_publish(exchange='', routing_key='debug', body='Hello World!')
print(" [x] Sent 'Hello World!'")

connection.close()
