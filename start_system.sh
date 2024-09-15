# create & start main service
docker compose -f docker-compose.yaml up -d --build

# start services:
# create & start yfin_scraper service
docker compose -f yfin_scraper/docker-compose.yaml up -d --build
# create & start fed_crawler service
docker compose -f fed_crawler/docker-compose.yaml up -d --build
