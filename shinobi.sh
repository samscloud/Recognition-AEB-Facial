#!/bin/bash

echo "Init Shinobi admin user"
docker cp super.json  Shinobi:/home/Shinobi/super.json
docker exec -it Shinobi pm2 restart camera.js
sleep 2
curl --location 'http://localhost:8080/super/testsuperlonngtokenvalueintheworld/accounts/registerAdmin' \
--header 'Content-Type: application/json' \
--data-raw '{
   "data": {
      "mail": "admin@admin.com",
      "pass": "zbi22121991",
      "password_again": "zbi22121991",
      "details": {
         "factorAuth": "0",
         "size": "10000",
         "days": "5",
         "event_days": "10",
         "log_days": "10",
         "max_camera": "",
         "permissions": "all",
         "edit_size": "1",
         "edit_days": "1",
         "edit_event_days": "1",
         "edit_log_days": "1",
         "use_admin": "1",
         "use_aws_s3": "1",
         "use_webdav": "1",
         "use_discordbot": "1",
         "use_ldap": "1"
      }
   }
}'