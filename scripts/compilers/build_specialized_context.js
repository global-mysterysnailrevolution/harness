#!/usr/bin/env node
/**
 * Specialized Context Compiler (Node.js)
 * Compiles specialized context packs for sub-agents
 */

const fs = require('fs');
const path = require('path');
const { execSync } = require('child_process');

// This is a wrapper that calls the Python version
// Full implementation would be in Node.js if needed

function buildSpecializedContext(options) {
    const {
        agentId,
        task,
        role,
        repoMap,
        contextPack,
        repo = '.',
        output
    } = options;

    const args = [
        'scripts/compilers/build_specialized_context.py',
        '--agent-id', agentId,
        '--task', task,
        '--role', role,
        '--repo', repo
    ];

    if (repoMap) args.push('--repo-map', repoMap);
    if (contextPack) args.push('--context-pack', contextPack);
    if (output) args.push('--output', output);

    try {
        execSync(`python ${args.join(' ')}`, { stdio: 'inherit' });
    } catch (e) {
        console.error('Error building specialized context:', e);
        process.exit(1);
    }
}

// CLI interface
if (require.main === module) {
    const args = process.argv.slice(2);
    const options = {};

    for (let i = 0; i < args.length; i += 2) {
        const key = args[i].replace('--', '');
        const value = args[i + 1];
        options[key] = value;
    }

    buildSpecializedContext(options);
}

module.exports = { buildSpecializedContext };
