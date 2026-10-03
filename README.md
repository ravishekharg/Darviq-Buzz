# Darviq Buzz

The backend of a social network, built as **11 microservices** to work through the problems large
social platforms face: a social graph, precomputed feeds, polyglot persistence, event-driven
fan-out and real alerting. It ships with a server-rendered web app, Docker Compose for local runs,
Kubernetes manifests, a Jenkins pipeline, and Terraform for Google Kubernetes Engine (GKE).

Built by [Darviq Systems](https://darviq.com).

## Features

- Sign-up and login (JWT for API clients, sessions for the web app)
- A **follow graph** and a separate **friend graph**; accepting a friend request follows both ways
- Posts with images, 6 reaction types, comments, reposts and hashtags
- A personalised feed, **precomputed when a post is written** (fan-out-on-write)
- Stories that expire after 24 hours
- Direct messages
- A notifications feed with an unread count (likes, comments, follows, friend requests)

## Architecture

```
Browser
  │
  ▼
web-bff  (Flask + Jinja: the server-rendered web app)
  │
  ├─▶ user-service           PostgreSQL   auth, profiles
  ├─▶ social-graph-service   Cassandra    follow and friend graphs
  ├─▶ post-service           Cassandra    posts, hashtags, reposts
  ├─▶ engagement-service     Cassandra    reactions, comments
  ├─▶ story-service          Cassandra    24-hour stories (TTL)
  ├─▶ messaging-service      Cassandra    direct messages
  ├─▶ feed-service           Cassandra    precomputed per-user timelines
  ├─▶ notification-service   PostgreSQL   notifications feed
  └─▶ media-service          PostgreSQL   image uploads (S3, with local fallback)

gateway  (Flask: JWT verification + reverse proxy, the public API for other clients)

RabbitMQ  (topic exchange "buzz.events")
  post.created, post.reposted          ──▶ feed-service          (fan-out to followers)
  post.liked, post.commented,
  post.reposted, user.followed,
  friend.request_*                     ──▶ notification-service
```

The web app is a trusted internal caller and talks to each service directly; the gateway is the
entry point for external API clients such as a future mobile app.

### Design decisions

**PostgreSQL and Cassandra, each where it fits.** Users, notifications and media need flexible
filtering, pagination and read-after-write consistency on modest tables, so they use PostgreSQL.
Graphs, posts, feeds, reactions, stories and messages are high-write and naturally partitioned by
user, so they use Cassandra. Each service's `models.py` explains its schema.

**Fan-out-on-write feeds.** When someone posts, `post-service` publishes an event; `feed-service`
looks up the author's followers and writes the post into each follower's own timeline partition.
Reading a feed is then a single partition read instead of a query across everyone you follow.

**Known trade-offs**, documented rather than hidden:
- The follower lookup during fan-out is a synchronous HTTP call with no retry or circuit breaker.
  A slow `social-graph-service` delays that fan-out; other messages are still processed.
- There are no foreign keys across services (they own separate databases), so deleting a user can
  leave orphaned rows in other services.
- Events are published without a transactional outbox; if RabbitMQ is down at publish time, the
  event is lost rather than retried.

## Running locally

Requires Docker and Docker Compose.

```bash
docker compose up -d --build
```

This starts PostgreSQL (3 databases), Cassandra (6 keyspaces), RabbitMQ, all 11 services,
Prometheus and Alertmanager. Open **http://localhost:8000** and sign up; no seed data is needed.

| Service | Port | | Service | Port |
|---|---|---|---|---|
| web-bff (the app) | 8000 | | feed-service | 5007 |
| gateway | 5000 | | notification-service | 5008 |
| user-service | 5001 | | media-service | 5009 |
| social-graph-service | 5002 | | Prometheus | 9090 |
| post-service | 5003 | | Alertmanager | 9093 |
| engagement-service | 5004 | | RabbitMQ management | 15672 |
| story-service | 5005 | | PostgreSQL | 5432 |
| messaging-service | 5006 | | Cassandra | 9042 |

The passwords in `docker-compose.yml`, `k8s/postgres.yaml` and the `.env.example` files are
**local development placeholders**. Replace them before deploying anywhere real.

### Running one service on its own

```bash
cd services/post-service
cp .env.example .env
pip install -r requirements.txt
python app.py
```

Point its `.env` at the PostgreSQL, Cassandra and RabbitMQ started by Compose.

## Monitoring and alerts

Every service exposes `/metrics` in Prometheus format. `prometheus/alerts.yml` defines:

- **ServiceDown**: a service stops answering. Tested by stopping a container: the alert fires in
  about 25 seconds, reaches Alertmanager, and clears when the service comes back.
- **Availability and latency SLO alerts** per service (99.9% availability, P99 under 1 second),
  using multi-window burn rates.
- **FeedFanoutStalled / NotificationConsumerStalled**: the asynchronous pipelines have stopped
  processing. At very low traffic these can't tell "broken" from "quiet"; the rule file says so.
- **MediaS3FallbackRateHigh**: uploads are going to local storage instead of S3. Expected locally,
  where there are no AWS credentials.

Alertmanager routes to a no-op receiver by default; add Slack, email or PagerDuty in
`alertmanager/alertmanager.yml`.

## Kubernetes

`k8s/` holds a Deployment and Service per microservice plus PostgreSQL, Cassandra, RabbitMQ,
Prometheus, Alertmanager, an ingress and NetworkPolicies.

- **Local cluster (kind):** `Jenkinsfile.homelab` builds all 11 images, loads them into a kind
  cluster and applies the manifests.
- **Google Cloud (GKE Autopilot):** `Terraform/gcp` creates the cluster and an Artifact Registry
  repository. `scripts/deploy-gcp.sh` builds and pushes the images, generates secrets and applies a
  GKE overlay (`k8s/gcp`), exposing the web app through a load balancer restricted to the IP range
  you allow.

```bash
cd Terraform/gcp && terraform init && terraform apply -var project_id=YOUR_PROJECT
PROJECT_ID=YOUR_PROJECT ALLOWED_CIDR=$(curl -s ifconfig.me)/32 ./scripts/deploy-gcp.sh
./scripts/teardown-gcp.sh   # remove it again
```

## Tested end to end

Against the full running stack, over real HTTP with browser-style sessions:

- The complete user journey: register, log in, post with an image, react, comment, repost, follow,
  send and accept a friend request (including the automatic mutual follow), post a story, send a
  message, receive a notification and mark it read.
- Fan-out: posting as one user and reading the precomputed feed of a follower.
- Failure handling: stopping a service and watching the alert fire and resolve.

Bugs found this way and fixed: media URLs missing the gateway's `/api` prefix, hand-written HTML
forms missing their CSRF token, and repost comments not reaching the precomputed feed.

## Limitations

- Direct messages poll every 3 seconds; there are no websockets.
- Lists (feed, profiles, hashtags, notifications) are capped rather than paginated.
- No rate limiting yet.
- `/discover` and the internal user listing scan all users; a search index would replace them at
  scale.

## Documentation

`Docs/Darviq-Buzz_HLD_v1.0.docx` is the high-level design document.
