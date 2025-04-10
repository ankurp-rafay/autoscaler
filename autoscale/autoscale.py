#!/usr/local/bin/python3

import json
import logging
import os
import requests
import sys
import time
import base64
from kubernetes import client, config


log_format = "%(asctime)s::%(levelname)s::%(message)s"
logging.basicConfig(level='INFO', format=log_format)
BASE_URL = os.environ['URL']
API_KEY = os.environ['RAFAY_API_KEY']
PROJECT = os.environ['PROJECT']
EM_ENV = os.environ['EM_ENV']
POD_PENDING_TIMER = os.environ['POD_PENDING_TIMER']

def send_request(method, url, headers, payload=None, verify=None):
    verify = True if verify is None else False
    if payload:
        return requests.request(method, url, headers=headers, data=payload, verify=verify)
    else:
        return requests.request(method, url, headers=headers, verify=verify)

def environment_status(headers):
    em_url_status = BASE_URL + "/apis/eaas.envmgmt.io/v1/projects/" + PROJECT + "/environments/" + EM_ENV + "/status"
    response = send_request('GET', em_url_status, headers)
    res = json.loads(response.text)
    status = res['status']['latest_events'][0]['triggerDetails']['status']
    logging.info("Trigger Event - %s", status)
    if status == 'success':
        workflow_state = res['status']['latest_events'][0]['workflowDetails']['state']
        logging.info("Workflow State - %s", workflow_state)
        if workflow_state == "complete":
            return "complete"
        if workflow_state == "inprogress":
            return "inprogress"
        if workflow_state == "pending":
            return "pending"
    elif status == 'pending':
       return "pending"
    else:
        return None

def auto_scale(headers):
    em_url = BASE_URL + "/apis/eaas.envmgmt.io/v1/projects/" + PROJECT + "/environments/" + EM_ENV
    response = send_request('GET', em_url, headers)
    res = json.loads(response.text)
    for i in range(len(res['spec']['variables'])):
        if res['spec']['variables'][i]['name'] == "total_nodes":
            print(res['spec']['variables'][i]['value'])
            new_count = int(res['spec']['variables'][i]['value']) + 1
            res['spec']['variables'][i]['value'] = str(new_count)
    payload = json.dumps(res)
    em_apply_url = BASE_URL + "/apis/eaas.envmgmt.io/v1/projects/" + PROJECT + "/environments"
    apply_response = send_request('POST', em_apply_url, headers, payload)
    if apply_response.status_code == 200:
        logging.info("Updated Environment with node count..")
        logging.info("Update Status Code - %d", apply_response.status_code)
        em_deploy_url = BASE_URL + "/apis/eaas.envmgmt.io/v1/projects/" + PROJECT + "/environments/" + EM_ENV + "/publish"
        deploy_response = send_request('POST', em_deploy_url, headers, {})
        logging.info("Deploy Status Code - %d", deploy_response.status_code)
    else:
        logging.info("Environment update failed..")
        logging.info("Status Code - %d", apply_response.status_code)
    return

def main():
    ##Download Kubeconfig
    v2_headers = {'X-RAFAY-API-KEYID': API_KEY, 'Content-Type': 'application/json'}
    headers = {'X-API-KEY': API_KEY, 'Content-Type': 'application/json'}
    kube_config_url = BASE_URL + "/v2/sentry/kubeconfig/user?opts.selector=rafay.dev/clusterName=" + EM_ENV
    response = send_request('GET', kube_config_url, v2_headers)
    res = json.loads(response.text)
    byte_data = base64.b64decode(res['data'])
    data = byte_data.decode("utf-8")
    with open("/config/kubeconfig.yaml", "w") as file:
        file.write(str(data))
    config.load_kube_config(config_file="/config/kubeconfig.yaml")
    v1 = client.CoreV1Api()
    while True:
        all_pods = v1.list_pod_for_all_namespaces(field_selector='status.phase=Pending')
        logging.info("Number of pending pods - %d", len(all_pods.items))
        if len(all_pods.items) > 0:
            status = environment_status(headers)
            if status == "complete":
                 time.sleep(int(POD_PENDING_TIMER))
                 check_pending_pods = v1.list_pod_for_all_namespaces(field_selector='status.phase=Pending')
                 if len(check_pending_pods.items) > 0:
                     logging.info("Trigger Autoscale for cluster - %s", EM_ENV)
                     auto_scale(headers)
                     time.sleep(int(POD_PENDING_TIMER))
            elif status == "inprogress":
                logging.info("Autoscale for cluster %s is inprogress..", EM_ENV)
                time.sleep(300)
            elif status == "pending":
                logging.info("Autoscale for cluster %s is pending..", EM_ENV)
                time.sleep(300)
        else:
            logging.info("All pods are in running state..")
            time.sleep(int(POD_PENDING_TIMER))


if __name__== "__main__":
    main()