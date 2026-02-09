#!/usr/bin/env node
/**
 * Deterministic Repo Map Compiler (Node.js)
 * Generates REPO_MAP.md from repository analysis
 */

const fs = require('fs');
const path = require('path');

function detectStack(repoPath) {
    const stack = {
        type: 'unknown',
        languages: [],
        frameworks: [],
        packageManager: null
    };
    
    const packageJsonPath = path.join(repoPath, 'package.json');
    if (fs.existsSync(packageJsonPath)) {
        stack.type = 'nodejs';
        stack.languages.push('javascript');
        stack.packageManager = 'npm';
        
        try {
            const pkg = JSON.parse(fs.readFileSync(packageJsonPath, 'utf8'));
            if (pkg.dependencies) {
                const deps = Object.keys(pkg.dependencies);
                if (deps.includes('react')) stack.frameworks.push('react');
                if (deps.includes('express')) stack.frameworks.push('express');
                if (deps.includes('next')) stack.frameworks.push('next');
            }
        } catch (e) {
            // Ignore parse errors
        }
    } else if (fs.existsSync(path.join(repoPath, 'requirements.txt'))) {
        stack.type = 'python';
        stack.languages.push('python');
        stack.packageManager = 'pip';
    } else if (fs.existsSync(path.join(repoPath, 'Cargo.toml'))) {
        stack.type = 'rust';
        stack.languages.push('rust');
        stack.packageManager = 'cargo';
    } else if (fs.existsSync(path.join(repoPath, 'go.mod'))) {
        stack.type = 'go';
        stack.languages.push('go');
        stack.packageManager = 'go';
    }
    
    return stack;
}

function findInsertionPoints(repoPath) {
    const insertionPoints = [];
    
    const commonDirs = [
        'src', 'lib', 'app', 'components', 'pages', 'routes',
        'scripts', 'workers', 'handlers', 'controllers', 'services'
    ];
    
    for (const dirName of commonDirs) {
        const dirPath = path.join(repoPath, dirName);
        if (fs.existsSync(dirPath)) {
            const stat = fs.statSync(dirPath);
            if (stat.isDirectory()) {
                insertionPoints.push({
                    path: dirName,
                    type: 'directory',
                    description: `Code directory: ${dirName}`
                });
            }
        }
    }
    
    const testDirs = ['tests', 'test', '__tests__', 'spec'];
    for (const testDir of testDirs) {
        const testPath = path.join(repoPath, testDir);
        if (fs.existsSync(testPath)) {
            insertionPoints.push({
                path: testDir,
                type: 'test_directory',
                description: `Test directory: ${testDir}`
            });
        }
    }
    
    return insertionPoints;
}

function generateRepoMap(repoPath, outputPath) {
    const stack = detectStack(repoPath);
    const insertionPoints = findInsertionPoints(repoPath);
    const timestamp = new Date().toISOString().replace('T', ' ').substring(0, 19);
    
    let content = `# Repository Map
Generated: ${timestamp}

## Stack
- Type: ${stack.type}
- Languages: ${stack.languages.length > 0 ? stack.languages.join(', ') : 'Unknown'}
- Frameworks: ${stack.frameworks.length > 0 ? stack.frameworks.join(', ') : 'None detected'}
- Package Manager: ${stack.packageManager || 'Unknown'}

## Architecture
- Repository Type: ${stack.type !== 'unknown' ? 'Code repository' : 'Documentation repository'}
- Structure: Detected from file system

## Insertion Points

`;
    
    if (insertionPoints.length > 0) {
        for (const point of insertionPoints) {
            content += `### ${point.path}\n`;
            content += `- Type: ${point.type}\n`;
            content += `- Description: ${point.description}\n\n`;
        }
    } else {
        content += 'No common insertion points detected. Repository may be empty or use non-standard structure.\n\n';
    }
    
    content += `## Status
- ✅ Repository structure mapped
- ✅ Insertion points identified
- ✅ Stack detected

## Notes
This map is generated deterministically from repository contents.
Update manually if structure changes significantly.
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
    let output = 'ai/context/REPO_MAP.md';
    let repo = '.';
    
    for (let i = 0; i < args.length; i++) {
        if (args[i] === '--output' && i + 1 < args.length) {
            output = args[i + 1];
            i++;
        } else if (args[i] === '--repo' && i + 1 < args.length) {
            repo = args[i + 1];
            i++;
        }
    }
    
    const repoPath = path.resolve(repo);
    const outputPath = path.join(repoPath, output);
    
    generateRepoMap(repoPath, outputPath);
}

if (require.main === module) {
    main();
}

module.exports = { generateRepoMap, detectStack, findInsertionPoints };
