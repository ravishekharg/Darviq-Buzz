-- Runs once on first container init. One database per SQL-backed service
-- (user-service, notification-service, media-service) on the same Postgres
-- instance -- the POSTGRES_USER superuser role owns each automatically, no
-- separate GRANT statements needed (unlike the MariaDB pattern used
-- elsewhere in this portfolio).
CREATE DATABASE buzz_users;
CREATE DATABASE buzz_notifications;
CREATE DATABASE buzz_media;
