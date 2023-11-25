# Use this file to remove the current catalog.db file and populate it with the newest version found in catalog.sql

echo "Updating database file"
# rm ./users/var/primary/fuse/users.db
# sqlite3 ./users/var/primary/fuse/users.db < ./users/var/users.sql
rm ./primary/fuse/users.db
sqlite3 ./primary/fuse/users.db < ./users.sql
echo "users Database file updated :)"
