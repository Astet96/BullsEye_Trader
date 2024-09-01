# set up network:
docker network create --driver bridge bullseye_trader || true

# start services:
# create & start yfin_scraper service
docker compose -f yfin_scraper/docker-compose.yaml up -d --build
# create & start fed_crawler service
docker compose -f fed_crawler/docker-compose.yaml up -d --build

# Store container ips to environment variables
export FED_CRAWLER="$(docker inspect  -f '{{range.NetworkSettings.Networks}}{{.IPAddress}}{{end}}' fed_crawler-api-1)"
export YFIN_SCRAPER="$(docker inspect  -f '{{range.NetworkSettings.Networks}}{{.IPAddress}}{{end}}' yfin_scraper-api-1)"

# create & start main service
docker compose -f docker-compose.yaml up -d --build
