#!/usr/bin/env python3
"""
HTTP wrapper for the MCP Tool Broker.
Exposes the broker CLI as a simple REST API on port 8000.
"""

import argparse
import sys
from pathlib import Path
from flask import Flask, request, jsonify

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
sys.path.insert(0, str(Path(__file__).parent))

from tool_broker import ToolBroker

app = Flask(__name__)
broker = None


def get_broker():
    global broker
    if broker is None:
        broker = ToolBroker()
    return broker


@app.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'ok', 'service': 'tool-broker'})


@app.route('/search', methods=['GET', 'POST'])
def search():
    data = request.get_json(silent=True) or {}
    query = data.get('query') or request.args.get('query', '')
    max_results = int(data.get('max_results', request.args.get('max_results', 10)))
    agent_id = data.get('agent_id') or request.args.get('agent_id')
    results = get_broker().search_tools(query=query, max_results=max_results, agent_id=agent_id)
    return jsonify(results)


@app.route('/describe', methods=['GET', 'POST'])
def describe():
    data = request.get_json(silent=True) or {}
    tool_id = data.get('tool_id') or request.args.get('tool_id', '')
    agent_id = data.get('agent_id') or request.args.get('agent_id')
    schema = get_broker().describe_tool(tool_id, agent_id)
    if schema:
        return jsonify(schema)
    return jsonify({'error': f'Tool not found: {tool_id}'}), 404


@app.route('/call', methods=['POST'])
def call_tool():
    data = request.get_json(silent=True) or {}
    tool_id = data.get('tool_id', '')
    tool_args = data.get('args', {})
    agent_id = data.get('agent_id')
    result = get_broker().call_tool(tool_id, tool_args, agent_id)
    return jsonify(result)


@app.route('/load', methods=['POST'])
def load_tools():
    data = request.get_json(silent=True) or {}
    tool_ids = data.get('tool_ids', [])
    agent_id = data.get('agent_id')
    if isinstance(tool_ids, str):
        tool_ids = [t.strip() for t in tool_ids.split(',')]
    tools = get_broker().load_tools(tool_ids, agent_id)
    return jsonify(tools)


@app.route('/pending', methods=['GET'])
def pending():
    pending_list = get_broker().allowlist_manager.get_pending_approvals()
    return jsonify(pending_list if pending_list else [])


@app.route('/approve', methods=['POST'])
def approve():
    data = request.get_json(silent=True) or {}
    request_id = data.get('request_id') or data.get('tool_id', '')
    agent_id = data.get('agent_id', 'api')
    override = data.get('override_vetting', False)
    result = get_broker().forge_approval.approve(
        request_id, approved_by=agent_id, override_vetting=override
    )
    if result.get('ok'):
        return jsonify(result)
    success = get_broker().allowlist_manager.approve_request(request_id)
    if success:
        return jsonify({'status': 'approved', 'request_id': request_id})
    return jsonify(result), 400


@app.route('/reject', methods=['POST'])
def reject():
    data = request.get_json(silent=True) or {}
    request_id = data.get('request_id') or data.get('tool_id', '')
    agent_id = data.get('agent_id', 'api')
    reason = data.get('reason', 'Rejected via API')
    success = get_broker().forge_approval.reject(request_id, rejected_by=agent_id, reason=reason)
    if not success:
        success = get_broker().allowlist_manager.reject_request(request_id, reason)
    if success:
        return jsonify({'status': 'rejected', 'request_id': request_id, 'reason': reason})
    return jsonify({'error': 'Request not found or already processed'}), 404


@app.route('/propose', methods=['POST'])
def propose():
    data = request.get_json(silent=True) or {}
    proposal = get_broker().forge_approval.propose_server(
        server_name=data.get('server_name', ''),
        source=data.get('source', ''),
        source_id=data.get('source_id', ''),
        proposed_by=data.get('agent_id', 'api'),
        source_path=data.get('source_path'),
    )
    return jsonify(proposal)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Tool Broker HTTP Server')
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=8000)
    parser.add_argument('--debug', action='store_true')
    args = parser.parse_args()
    print(f'Starting Tool Broker HTTP server on {args.host}:{args.port}')
    app.run(host=args.host, port=args.port, debug=args.debug)
