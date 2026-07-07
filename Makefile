install:
	python -m pip install -r requirements.txt

test:
	python -m unittest discover -s tests

run:
	uvicorn app.main:app --reload

check:
	python -m compileall app
	python -m unittest discover -s tests

docker-build:
	docker build -t ai-k8s-agent:local .

k8s-apply:
	kubectl apply -f k8s/namespace.yaml
	kubectl apply -f k8s/serviceaccount.yaml
	kubectl apply -f k8s/rbac.yaml
	kubectl apply -f k8s/deployment.yaml
	kubectl apply -f k8s/service.yaml

k8s-status:
	kubectl get deploy,pods,svc,sa -n ai-k8s-agent
	kubectl get role,rolebinding -n demo-apps

k8s-port-forward:
	kubectl port-forward svc/ai-k8s-agent -n ai-k8s-agent 8000:8000

demo-apply:
	kubectl apply -f broken-nginx.yaml && kubectl apply -f crashloop-app.yaml && kubectl apply -f pending-app.yaml

demo-status:
	kubectl get deploy,pods,rs,svc,endpoints -n demo-apps
