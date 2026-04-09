# Makefile — SO-ARM101 channel image builds
#
# Channels:
#   app       — shared application image (arm64); base for chi-edge and balena
#   chi-edge  — app + openssh-server + entrypoint; managed by Chameleon CHI@Edge
#   balena    — app + balena supervisor label; managed by balena cloud
#   local     — no build needed; runs app image directly (see channels/local/)
#   dev       — x86_64 simulation/development image
#
# Typical workflow:
#   make push-chi-edge     # rebuild app + chi-edge, push both
#   make push-balena       # rebuild app + balena, push both

REGISTRY  = rianders
APP       = lerobot-soarm101

APP_TAG   = $(REGISTRY)/$(APP):app
CHI_TAG   = $(REGISTRY)/$(APP):chi-edge
BAL_TAG   = $(REGISTRY)/$(APP):balena
DEV_TAG   = $(REGISTRY)/$(APP):dev
LATEST    = $(REGISTRY)/$(APP):latest

BUILDX    = docker buildx build --platform linux/arm64

.PHONY: build-app build-chi-edge build-balena build-dev \
        push-app push-chi-edge push-balena push-dev \
        push-all build-all

# ── Build targets ──────────────────────────────────────────────────────────────

build-app:
	$(BUILDX) --load -t $(APP_TAG) -f channels/app/Dockerfile .

build-chi-edge: build-app
	$(BUILDX) --load -t $(CHI_TAG) -t $(LATEST) -f channels/chi-edge/Dockerfile .

build-balena: build-app
	$(BUILDX) --load -t $(BAL_TAG) -f channels/balena/Dockerfile .

build-dev:
	docker buildx build --platform linux/amd64 --load \
	  -t $(DEV_TAG) -f channels/dev/Dockerfile .

build-all: build-chi-edge build-balena build-dev

# ── Push targets ───────────────────────────────────────────────────────────────

push-app: build-app
	docker push $(APP_TAG)

push-chi-edge: build-chi-edge push-app
	docker push $(CHI_TAG)
	docker push $(LATEST)

push-balena: build-balena push-app
	docker push $(BAL_TAG)

push-dev: build-dev
	docker push $(DEV_TAG)

push-all: push-chi-edge push-balena push-dev
