#!/usr/bin/python
# -*- coding: utf-8 -*-

import pika

params = pika.URLParameters('amqp://admin:admin@192.168.1.230')
connection = pika.BlockingConnection(params)
channel = connection.channel()

channel.queue_declare(queue='debug')

def callback(ch, method, properties, body):
  print(" [x] Received %r" % body)

channel.basic_consume(callback,
                      queue='debug',
                      no_ack=True)

print(' [*] Waiting for messages:')
channel.start_consuming()