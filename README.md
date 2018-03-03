# Clúster RabbitMQ + Failover HAProxy

En el siguiente documento voy a explicar todos los pasos a seguir para montar un clúster formado por 3 nodos de **RabbitMQ** y 2 servidores de **HAProxy** con **Keepalived**, de tal forma que en caso de la perdida de uno de los nodos de RabbitMQ podamos seguir teniendo disponibles los otros dos y nuestro sistema pueda seguir funcionando con total normalidad.
Los servidores HAProxy junto con Keepalived se encargaran de balancear la carga entre los diferentes nodos de RabbitMQ y si sufrimos la perdida de uno de los servidores HAProxy entrará automáticamente el otro en funcionamiento.

Todos los servidores van a estar corriendo bajo **Ubuntu Server 16.04**.


# Esquema de Red

En el siguiente esquema podemos ver los diferentes servidores que van a formar nuestro sistema y sus correspondientes Hostname y direcciones IP.

De cara al cliente que realice las peticiones solo dispondrá de una dirección IP virtual que en este caso será 192.168.1.230.

![Esquema de red para un cluster de RabbitMQ y HAProxy](https://github.com/RafaMunoz/Cluster-RabbitMQ-HAProxy/blob/master/img/esquema_red_cluster_rabbitmq.png)

# Configuración basica

En este apartado veremos las configuraciones básicas que se tiene que realizar en cada servidor teniendo en cuenta sus direcciones IP y su Hostname.

Actualizamos el listado de los repositorios y a continuación actualizaremos los paquetes.
 
	sudo apt update
	sudo apt upgrade
	    
Le pondremos a cada servidor una dirección IP fija.

     sudo nano /etc/network/interfaces
	    
Un ejemplo de la configuración  de unos de los servidores puede ser la siguiente:

    auto enp0s3
    iface enp0s3 inet static
    address 192.168.1.201
    gateway 192.168.1.1
    netmask 255.255.255.0
    network 192.168.1.0
    broadcast 192.168.1.255
    dns-nameservers 8.8.8.8 8.8.4.4

Si durante la instalación del sistema operativo no hemos puesto el nombre de hostname correctamente o hemos partido de un clon de una máquina virtual, lo cambiaremos por el que corresponda.

    sudo nano /etc/hostname

Por ejemplo, en uno de ellos podemos poner:

    rabbit_01
 
Seguidamente también lo cambiaremos en el archivo host:

    sudo nano /etc/hosts

En el caso de los nodos de RabbitMQ, además de cambiar su nombre, también tenemos que añadir el Hostname y la Dirección IP de los otros dos nodos.
Este es un ejemplo del archivo hosts del nodo 1:

    127.0.1.1       rabbit_01
    192.168.1.202   rabbit_02
    192.168.1.203   rabbit_03

Reiniciaremos los servidores para que cojan los cambios.

    sudo reboot
 
 
# Instalación del Clúster RabbitMQ
Antes de crear el clúster tenemos que agregar varios repositorios e instalar alguna dependencia.

## Instalación de Erlang

RabbitMQ necesita de Erlang para funcionar. Para ello primero debemos añadir su repositorio a nuestro sistema ejecutando los siguientes dos comandos:

    wget https://packages.erlang-solutions.com/erlang-solutions_1.0_all.deb
    sudo dpkg -i erlang-solutions_1.0_all.deb

Actualizamos el listado del repositorio.

    sudo apt update
  
Procedemos con la instalación de Erlang.
  

    sudo apt-get install erlang


## Instalación de RabbitMQ

Antes de crear el clúster de RabbitMQ, necesitamos instalar RabbitMQ por separado en cada nodo.

Agregaremos el repositorio de RabbitMQ a nuestro sistema y su clave pública.

    echo "deb https://dl.bintray.com/rabbitmq/debian xenial main" | sudo tee /etc/apt/sources.list.d/bintray.rabbitmq.list
    wget -O- https://www.rabbitmq.com/rabbitmq-release-signing-key.asc | sudo apt-key add -

Volvemos a actualizar la lista de los repositorios.

    sudo apt-get update

Instalamos RabbitMQ.

    sudo apt-get install rabbitmq-server

Habilitamos el plugin para acceder vía web.

    sudo rabbitmq-plugins enable rabbitmq_management

En caso de que vayamos a utilizar federaciones necesitaremos habilitar el plugin **rabbitmq_federation** y **rabbitmq_federation_management**. Para ello debemos ejecutar los dos siguientes comandos en todos los nodos de RabbitMQ.

    sudo rabbitmq-plugins enable rabbitmq_federation
    sudo rabbitmq-plugins enable rabbitmq_federation_management

Creamos un usuario con su contraseña para poder acceder. En este caso el usuario será **admin** y la contraseña **admin**.

    sudo rabbitmqctl add_user admin admin
    sudo rabbitmqctl set_user_tags admin administrator
    sudo rabbitmqctl set_permissions -p / admin ".*" ".*" ".*"
  
Ahora podemos irnos a un navegador web y poner la dirección IP de uno de los nodos junto al puerto 15672 y vemos cómo podemos acceder a la administración de RabbitMQ.

 - Nodo 1: http://192.168.1.201:15672 
 - Nodo 2: http://192.168.1.202:15672
 - Nodo 3: http://192.168.1.203:15672


Por defecto nuestro sistema se configura en modo desarrollo con un **File Descriptor = 1024**. Para entornos de producción se recomienda al menos aumentar ese valor a 65536.

Para cambiar ese valor editaremos el archivo rabbitmq-server.service. 

    sudo nano /etc/systemd/system/multi-user.target.wants/rabbitmq-server.service

Buscamos el settings **LimitNOFILE**, le descomentamos y le ponemos el valor 65536.

    LimitNOFILE=65536

Como las peticiones las vamos a realizar a través de un proxy, si en la web de RabbitMQ queremos ver la dirección IP del cliente que realiza la conexión, en vez de la dirección IP del proxy necesitamos añadir un setting (**proxy_protocol = true**) en el fichero de configuración **rabbitmq.conf**.
>Este setting le deberemos añadir en todos los nodos, y una vez puesto, el nodo solo aceptara conexiones desde HAProxy, no se podrán hacer peticiones directas a la dirección IP del nodo de RabbitMQ.

    sudo nano /etc/rabbitmq/rabbitmq.conf

Y añadimos:

    proxy_protocol = true

Recargamos systemctl para que coja el cambio realizado.
 

    sudo systemctl daemon-reload

Reiniciamos el servicio de RabbitMQ, entramos en la web y en las estadísticas podemos ver cómo ha aumentado el valor de File Descriptor.

    sudo service rabbitmq-server restart


## Configuración del Clúster

Para formar el clúster y que todos los nodos funcionen en conjunto es necesario que todos tengan la misma cookie de Erlang. Para ello entramos en el nodo principal que en este caso será **rabbit_01** y consultamos su cookie. Esta la deberemos copiar a los otros dos nodos para que sea la misma.

    sudo nano /var/lib/rabbitmq/.erlang.cookie

Ahora deberemos configurar el archivo **rabbitmq-env.conf** de cada nodo donde pondremos el nombre del nodo. Este estará formado por **rabbit@[hostname]**.

    sudo nano/etc/rabbitmq/rabbitmq-env.conf

En el caso del primer nodo sería:

    NODENAME=rabbit@rabbit_01

Reiniciamos RabbitMQ para que coja el último cambio:

    sudo service rabbitmq-server restart


Podemos consultar el estado de cada nodo y ver como todavía son independientes.

    sudo rabbitmqctl cluster_status

Respuesta del nodo 1:

    Cluster status of node rabbit@rabbit_01 ...
    [{nodes,[{disc,[rabbit@rabbit_01]}]},{running_nodes,[rabbit@rabbit_01]}]
    ...done.

Ahora uniremos el nodo 2 (rabbit_02) con el nodo 1 (rabbit_01) que será el maestro.

    sudo rabbitmqctl stop_app
    sudo rabbitmqctl join_cluster rabbit@rabbit_01
    sudo rabbitmqctl start_app

A continuación, unimos el nodo 3 (rabbit_03) con el nodo 2 (rabbit_02)

    sudo rabbitmqctl stop_app
    sudo rabbitmqctl join_cluster rabbit@rabbit_02
    sudo rabbitmqctl start_app

Una vez hecho esto si consultamos el estado de cada clúster podemos ver como ya están unidos.

Respuesta del nodo 1:

    rabbit_01$ rabbitmqctl cluster_status
    Cluster status of node rabbit@rabbit_01 ...
    [{nodes,[{disc,[rabbit@rabbit_01,rabbit@rabbit_02,rabbit@rabbit_03]}]},
    {running_nodes,[rabbit@rabbit_03,rabbit@rabbit_02,rabbit@rabbit_01]}]
    ...done.


Respuesta del nodo 2:

    rabbit_02$ rabbitmqctl cluster_status
    Cluster status of node rabbit@rabbit_02 ...
    [{nodes,[{disc,[rabbit@rabbit_01,rabbit@rabbit_02,rabbit@rabbit_03]}]},
    {running_nodes,[rabbit@rabbit_03,rabbit@rabbit_01,rabbit@rabbit_02]}]
    ...done.

Respuesta del nodo 3:

    rabbit_03$ rabbitmqctl cluster_status
    Cluster status of node rabbit@rabbit_03 ...
    [{nodes,[{disc,[rabbit@rabbit_03,rabbit@rabbit_02,rabbit@rabbit_01]}]},
    {running_nodes,[rabbit@rabbit_02,rabbit@rabbit_01,rabbit@rabbit_03]}]
    ...done.

Si vamos a la web de uno de los RabbitMQ podemos observar cómo nos aparece la información de los tres nodos.

![Cluster RabbitMQ](https://github.com/RafaMunoz/Cluster-RabbitMQ-HAProxy/blob/master/img/cluster_rabbitmq.png)


# Instalación de HAProxy

Una vez tenemos preparado el clúster de RabbitMQ vamos a proceder a crear el balanceo y failover de HAProxy.

## Instalación y configuración HAProxy
Instalaremos y configuraremos el balanceo de las peticiones que recibirá nuestro servidor.

    sudo apt-get install haproxy

Editamos la configuración del archivo **haproxy.cfg** y será igual para los dos servidores excepto en el apartado de estadísticas que configuraremos la dirección IP del servidor HAProxy que estamos configurando.

    sudo nano /etc/haproxy/haproxy.cfg

Esta configuración está formada por varios apartados:

    listen rabbitmq
        bind 0.0.0.0:5672
        mode tcp
        balance roundrobin
        timeout client 3h
        timeout server 3h
        option clitcpka
        maxconn 176670
        server rabbit01 192.168.1.201:5672 check fall 3 rise 2 send-proxy-v2 maxconn 58890
        server rabbit02 192.168.1.202:5672 check fall 3 rise 2 send-proxy-v2 maxconn 58890
        server rabbit03 192.168.1.203:5672 check fall 3 rise 2 send-proxy-v2 maxconn 58890
        
	listen rabbitmq_management
        bind 0.0.0.0:15672
        mode tcp
        balance roundrobin
        server rabbit01 192.168.1.201:15672 check fall 3 rise 2
        server rabbit02 192.168.1.202:15672 check fall 3 rise 2
        server rabbit03 192.168.1.203:15672 check fall 3 rise 2
        
    listen stats
	    bind 192.168.1.210:8181
	    stats enable
	    stats uri /
	    stats realm Haproxy\ Statistics
	    stats auth admin:admin
	    stats refresh 5s

 1. En **"listen rabbitmq"** indicaremos que todo lo que se reciba por el puerto **5672** será balanceado con el mismo peso (roundrobin) a cada nodo de RabbitMQ. 
Estos nodos van a ser dados por inactivos si se producen tres comprobaciones erroneas seguidas y se volverá a tomar como activo al recibir dos comprobaciones correctas. 
Por defecto se realizan cada 2000ms pero es configurable.

	Para no tener desconexiones de los clientes se configura un **timeout client** y un **timeout server** de 3 horas y añadimos la configuración **option clitcpka** para que se envíen paquetes de Heartbeat al lado del cliente y no se pierda la conexión.
	
	El setting **maxconn** se configura con 176670 ya que anteriormente hemos configurado cada nodo de RabbitMQ con 65536 y eso permite 58890 conexiones por nodo.

    **send-proxy-v2** permite que a RabbitMQ le llegue la dirección IP del cliente que realiza la conexión, en vez de la dirección IP del HAProxy.

 2. El apartado de **rabbitmq_management** será para la gestión de RabbitMQ a través del navegador web.

 3. Por último en **listen stats** le diremos que todo lo que se pida a la IP del HAProxy que estamos configurando y al puerto 8181 será para mostrar las estadísticas de conexiones y balanceo de carga que está realizando. 
Esta información la podremos ver haciendo una petición a través del navegador web y con el usuario **admin** y contraseña **admin** configurados en el setting **stats auth**.


## Instalación y configuración de Keepalived
Es hora de instalar Keepalived que sera el software instalado en los servidores de HAProxy para crear el failover entre ellos y proporcionar una IP virtual para que los clientes realicen las peticiones.

Instalamos Keepalived.

    sudo apt-get install keepalived

Configuraremos el archivo **keepalived.conf** que tendrá una configuración diferente para cada servidor.

    sudo nano /etc/keepalived/keepalived.conf

Los settings más importantes de cada configuración son:

 - **interface**: donde indicamos la tarjeta de red de nuestro servidor.
 - **state**: le decimos cual va a ser el MASTER y cual el BACKUP.
 - **priority**: daremos más prioridad al servidor maestro de tal forma que en caso de que los dos servidores HAProxy estén iniciados tomará toda la carga de conexiones.
 - **virtual_router_id**: identificador numérico que tiene que ser igual en los dos servidores.
 - **auth_pass**: especifica la contraseña utilizada para autenticar los servidores en la sincronización de failover.
 - **virtual_ipaddress**: sera la dirección IP virtual que compartirán lo dos servidores y a la que tienen que realizar las peticiones los clientes.

Configuración servidor **MASTER**:

    vrrp_script chk_haproxy {
	    script "pidof haproxy"
	    interval 2
    }
    
	vrrp_instance VI_1 {
	    interface enp0s3
	    state MASTER
	    priority 200

	    virtual_router_id 33

	    authentication {
	        auth_type PASS
	        auth_pass 129348
	    }

	    virtual_ipaddress {
	        192.168.1.230/24
	    }

	    track_script {
	        chk_haproxy
	    }
	}

Configuración servidor **BACKUP**:

    vrrp_script chk_haproxy {
	    script "pidof haproxy"
	    interval 2
    }
    vrrp_instance VI_1 {
	    interface enp0s3
	    state BACKUP
	    priority 100

	    virtual_router_id 33

	    authentication {
	        auth_type PASS
	        auth_pass 129348
	    }

	    virtual_ipaddress {
	        192.168.1.230/24
	    }
    
	    track_script {
	        chk_haproxy
	    }
	}

