#!/usr/bin/env node
/**
 * Deterministic Context Pack Compiler (Node.js)
 * Generates CONTEXT_PACK.md from context artifacts
 */

const fs = require('fs');
const path = require('path');

function compileContextPack(repoPath, outputPath, inputFile = null) {
    const timestamp = new Date().toISOString().replace('T', ' ').substring(0, 19);
    
    let repoMap = '';
    const repoMapPath = path.join(repoPath, 'ai/context/REPO_MAP.md');
    if (fs.existsSync(repoMapPath)) {
        repoMap = fs.readFileSync(repoMapPath, 'utf8');
    }
    
    let featureResearch = '';
    const researchPath = path.join(repoPath, 'ai/context/FEATURE_RESEARCH.md');
    if (fs.existsSync(researchPath)) {
        featureResearch = fs.readFileSync(researchPath, 'utf8');
    }
    
    let inputContent = '';
    if (inputFile && fs.existsSync(inputFile)) {
        inputContent = fs.readFileSync(inputFile, 'utf8');
    }
    
    let content = `# Context Pack
Generated: ${timestamp}

## Purpose
This context pack provides essential information for AI agents working with this repository.

## Repository Overview

**Stack**: Detected from repository structure
**Architecture**: See REPO_MAP.md for details

## Key Context

### Repository Structure
`;
    
    if (repoMap) {
        const lines = repoMap.split('\n');
        let inStack = false;
        for (const line of lines) {
            if (line.includes('## Stack')) {
                inStack = true;
            }
            if (inStack && line.trim() && !line.startsWith('#')) {
                content += line + '\n';
            }
            if (inStack && line.startsWith('##') && !line.includes('Stack')) {
                break;
            }
        }
    } else {
        content += 'Repository structure not yet mapped. Run context priming.\n';
    }
    
    content += '\n### Feature Research\n\n';
    
    if (featureResearch) {
        content += featureResearch.substring(0, 1000);
        if (featureResearch.length > 1000) {
            content += '\n\n[... truncated - see FEATURE_RESEARCH.md for full content]\n';
        }
    } else {
        content += 'No feature research available yet.\n';
    }
    
    if (inputContent) {
        content += '\n### Additional Context\n\n';
        content += inputContent.substring(0, 500);
    }
    
    content += `

## Agent Guidelines

### Before Making Changes
1. ✅ Consult \`ai/context/REPO_MAP.md\` for structure
2. ✅ Review \`ai/context/CONTEXT_PACK.md\` for context (this file)
3. ✅ Check \`ai/memory/WORKING_MEMORY.md\` for recent state
4. ✅ Verify no locks in \`ai/_locks/\` for target files

### During Operations
- Use parallel workers when appropriate
- Follow safety gates for sensitive operations
- Checkpoint memory after significant changes

### After Operations
- Update \`ai/memory/WORKING_MEMORY.md\` with new state
- Run validation tests if applicable
- Document changes in appropriate context files

## Status
- ✅ Context pack ready
- ✅ Guidelines defined
- ✅ Safety gates documented

## Last Updated
${timestamp}
`;
    
    const outputDir = path.dirname(outputPath);
    if (!fs.existsSync(outputDir)) {
        fs.mkdirSync(outputDir, { recursive: true });
    }
    
    fs.writeFileSync(outputPath, content, 'utf8');
    console.log(`✓ Generated: ${outputPath}`);
}

function main() {
    const args = process.argv.slice(2);
    let output = 'ai/context/CONTEXT_PACK.md';
    let input = null;
    let repo = '.';
    
    for (let i = 0; i < args.length; i++) {
        if (args[i] === '--output' && i + 1 < args.length) {
            output = args[i + 1];
            i++;
        } else if (args[i] === '--input' && i + 1 < args.length) {
            input = args[i + 1];
            i++;
        } else if (args[i] === '--repo' && i + 1 < args.length) {
            repo = args[i + 1];
            i++;
        }
    }
    
    const repoPath = path.resolve(repo);
    const outputPath = path.join(repoPath, output);
    const inputPath = input ? path.resolve(input) : null;
    
    compileContextPack(repoPath, outputPath, inputPath);
}

if (require.main === module) {
    main();
}

module.exports = { compileContextPack };
