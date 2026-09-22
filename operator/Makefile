VERSION ?= 0.19.0
GIT_TAG := operator_v$(VERSION)

KUBECTL := kubectl
KUBECTL_DELETE := $(KUBECTL) delete --ignore-not-found

.PHONY: deploy
deploy:
	$(KUBECTL) apply -k .

.PHONY: undeploy
undeploy:
	-$(KUBECTL_DELETE) -k .

.PHONY: get-tag
get-tag:
	@echo $(GIT_TAG)

.PHONY: clean
clean:
	rm -rf output

prep-release:
	@rm -rf output
	@mkdir -p output/addons
	@echo "Running kustomize build on ./ (full install)"
	kustomize build . > ./output/install.yaml
	@echo "Running kustomize build on ./controller/"
	kustomize build ./controller/ > ./output/keip-core-controller.yaml
	@for dir in ./controller/addons/*/ ; do \
		echo "Running kustomize build on $$dir" ; \
		addon=$$(basename $$dir) ; \
		mkdir -p output/addons/$$addon ; \
		kustomize build $$dir >> ./output/addons/$$addon/addon-$${addon}-controller.yaml ; \
		echo "---" >> ./output/addons/all-addons.yaml ; \
		kustomize build $$dir >> ./output/addons/all-addons.yaml ; \
	done
	@echo "Running kustomize build on ./crd/"
	kustomize build ./crd/ > ./output/crd.yaml
	@echo "Files that will be released:"
	@find ./output -type f

metacontroller/deploy:
	$(KUBECTL) apply -k metacontroller

metacontroller/undeploy:
	-$(KUBECTL_DELETE) -k metacontroller

controller/deploy: crd/deploy
	$(KUBECTL) apply -k controller

controller/undeploy: crd/undeploy
	-$(KUBECTL_DELETE) -k controller

addons/certmanager/deploy:
	$(KUBECTL) apply -k controller/addons/certmanager

addons/certmanager/undeploy:
	$(KUBECTL_DELETE) -k controller/addons/certmanager

crd/deploy:
	$(KUBECTL) apply -k crd

crd/undeploy:
	-$(KUBECTL_DELETE) -k crd
