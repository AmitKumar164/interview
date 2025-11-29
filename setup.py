'''
Step 1 -> sudo apt install postgresql postgresql-contrib
Step 2 -> pip install psycopg[binary]
Step 3 -> sudo -u postgres psql
Step 4 -> CREATE USER bulkhiring WITH PASSWORD 'bulkhiring';
Step 5 -> CREATE DATABASE bulkhiring_db OWNER bulkhiring;
Step 6 -> GRANT ALL PRIVILEGES ON DATABASE bulkhiring_db TO bulkhiring;
Step 7 -> \q
Step 8 -> sudo nano /etc/postgresql/<your_version>/main/pg_hba.conf
Step 9 -> Make it like below
################################################################################
# DO NOT DISABLE!
# If you change this first entry you will need to make sure that the
# database superuser can access the database using some other method.
# Noninteractive access to all databases is required during automatic
# maintenance (custom daily c\qronjobs, replication, and similar tasks).
#
# Database administrative login by Unix domain socket
local   all             postgres                                peer

# TYPE  DATABASE        USER            ADDRESS                 METHOD

# "local" is for Unix domain socket connections only
local   all             all                                     md5
# IPv4 local connections:
host    all             all             127.0.0.1/32            md5
# IPv6 local connections:
host    all             all             ::1/128                 md5
# Allow replication connections from localhost, by a user with the
# replication privilege.
local   replication     all                                     peer
host    replication     all             127.0.0.1/32            md5
host    replication     all             ::1/128                 md5
################################################################################
Step 10 -> sudo service postgresql restart
Step 11 -> psql -U bulkhiring -d bulkhiring_db -h localhost -W 
'''
