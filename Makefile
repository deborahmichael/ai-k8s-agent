install:
	python -m pip install -r requirements.txt

test:
	python -m unittest discover -s tests

run:
	uvicorn app.main:app --reload

check:
	python -m compileall app
	python -m unittest discover -s tests

demo-apply:
	kubectl apply -f broken-nginx.yaml && kubectl apply -f crashloop-app.yaml && kubectl apply -f pending-app.yaml

demo-status:
	kubectl get deploy,pods,rs,svc,endpoints -n demo-apps
