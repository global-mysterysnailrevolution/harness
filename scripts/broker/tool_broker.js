#!/usr/bin/env node
/**
 * MCP Tool Broker (Node.js)
 * Provides unified tool access with discovery, allowlisting, and on-demand hydration
 */

const fs = require('fs');
const path = require('path');
const { execSync } = require('child_process');

class ToolBroker {
    constructor(configPath = null) {
        this.toolSchemasCache = {};
        this.configPath = configPath;
        this.discovery = new ToolDiscovery();
        this.allowlistManager = new AllowlistManager();
    }

    searchTools(query, options = {}) {
        const {
            tags = null,
            allowServers = null,
            maxResults = 10,
            agentId = null
        } = options;

        // Discover tools if not cached
        if (!this.discovery.toolsCache || Object.keys(this.discovery.toolsCache).length === 0) {
            this.discovery.discoverToolsFromMcpServers();
        }

        // Apply server allowlist if agent specified
        let finalAllowServers = allowServers;
        if (agentId) {
            const agentServers = this.allowlistManager.getAllowedServers(agentId);
            if (agentServers && agentServers.length > 0) {
                finalAllowServers = agentServers;
            }
        }

        // Search tools
        let results = this.discovery.searchTools(
            query,
            tags,
            finalAllowServers,
            maxResults
        );

        // Filter by agent allowlist
        if (agentId) {
            results = this.allowlistManager.filterToolsByAllowlist(agentId, results);
        }

        // Return lightweight metadata
        return results.map(r => ({
            tool_id: r.tool_id,
            name: r.name,
            short_desc: r.short_desc,
            server: r.server,
            confidence: r.confidence
        }));
    }

    describeTool(toolId, agentId = null) {
        // Check allowlist
        if (agentId && !this.allowlistManager.isToolAllowed(agentId, toolId)) {
            return null;
        }

        // Check cache first
        if (this.toolSchemasCache[toolId]) {
            return this.toolSchemasCache[toolId];
        }

        // Get from discovery
        const schema = this.discovery.getToolSchema(toolId);
        if (schema) {
            this.toolSchemasCache[toolId] = schema;
        }

        return schema;
    }

    callTool(toolId, args, agentId = null) {
        // Check allowlist
        if (agentId && !this.allowlistManager.isToolAllowed(agentId, toolId)) {
            return {
                error: "Tool not allowed for this agent",
                tool_id: toolId
            };
        }

        // Get tool schema
        const schema = this.describeTool(toolId, agentId);
        if (!schema) {
            return {
                error: "Tool not found",
                tool_id: toolId
            };
        }

        // Extract server from tool_id
        const serverName = toolId.includes(':') ? toolId.split(':')[0] : 'unknown';

        // In production, this would make actual MCP call
        return {
            tool_id: toolId,
            server: serverName,
            args: args,
            result: "Tool call would be executed here via MCP client",
            note: "Implement actual MCP client integration"
        };
    }

    loadTools(toolIds, agentId = null) {
        const tools = [];

        for (const toolId of toolIds) {
            // Check allowlist
            if (agentId && !this.allowlistManager.isToolAllowed(agentId, toolId)) {
                continue;
            }

            const schema = this.describeTool(toolId, agentId);
            if (schema) {
                tools.push(schema);
            }
        }

        return tools;
    }
}

class ToolDiscovery {
    constructor(mcpConfigPath = null) {
        this.mcpConfigPath = mcpConfigPath || this.findMcpConfig();
        this.toolsCache = {};
    }

    findMcpConfig() {
        const configLocations = [
            path.join(require('os').homedir(), '.cursor', 'User', 'settings.json'),
            path.join(require('os').homedir(), '.config', 'cursor', 'settings.json'),
            path.join(process.cwd(), '.cursor', 'mcp.json')
        ];

        for (const loc of configLocations) {
            if (fs.existsSync(loc)) {
                return loc;
            }
        }

        return null;
    }

    discoverToolsFromMcpServers() {
        if (!this.mcpConfigPath || !fs.existsSync(this.mcpConfigPath)) {
            return {};
        }

        let config;
        try {
            config = JSON.parse(fs.readFileSync(this.mcpConfigPath, 'utf8'));
        } catch (e) {
            console.error(`Error reading MCP config: ${e}`);
            return {};
        }

        const mcpServers = config.mcp?.servers || config['mcp.servers'] || {};
        const allTools = {};

        for (const [serverName, serverConfig] of Object.entries(mcpServers)) {
            const tools = this.listToolsFromServer(serverName, serverConfig);
            if (tools && tools.length > 0) {
                allTools[serverName] = tools;
            }
        }

        this.toolsCache = allTools;
        return allTools;
    }

    listToolsFromServer(serverName, serverConfig) {
        // Would use actual MCP client in production
        return [];
    }

    searchTools(query, tags = null, allowServers = null, maxResults = 10) {
        if (!this.toolsCache || Object.keys(this.toolsCache).length === 0) {
            this.discoverToolsFromMcpServers();
        }

        const results = [];
        const queryLower = query.toLowerCase();

        for (const [serverName, tools] of Object.entries(this.toolsCache)) {
            if (allowServers && !allowServers.includes(serverName)) {
                continue;
            }

            for (const tool of tools) {
                const toolName = (tool.name || '').toLowerCase();
                const toolDesc = (tool.description || '').toLowerCase();

                if (toolName.includes(queryLower) || toolDesc.includes(queryLower)) {
                    results.push({
                        tool_id: `${serverName}:${tool.name || ''}`,
                        name: tool.name || '',
                        short_desc: (tool.description || '').substring(0, 100),
                        server: serverName,
                        confidence: this.calculateConfidence(query, tool),
                        schema: tool
                    });
                }
            }
        }

        results.sort((a, b) => b.confidence - a.confidence);
        return results.slice(0, maxResults);
    }

    calculateConfidence(query, tool) {
        const queryLower = query.toLowerCase();
        const toolName = (tool.name || '').toLowerCase();
        const toolDesc = (tool.description || '').toLowerCase();

        let confidence = 0.0;

        if (queryLower === toolName) {
            confidence += 1.0;
        } else if (toolName.includes(queryLower)) {
            confidence += 0.8;
        } else if (toolDesc.includes(queryLower)) {
            confidence += 0.5;
        }

        return confidence;
    }

    getToolSchema(toolId) {
        const [serverName, toolName] = toolId.includes(':') 
            ? toolId.split(':', 2) 
            : [null, toolId];

        if (!this.toolsCache || Object.keys(this.toolsCache).length === 0) {
            this.discoverToolsFromMcpServers();
        }

        if (serverName && this.toolsCache[serverName]) {
            for (const tool of this.toolsCache[serverName]) {
                if (tool.name === toolName) {
                    return tool;
                }
            }
        }

        // Search all servers
        for (const tools of Object.values(this.toolsCache)) {
            for (const tool of tools) {
                if (tool.name === toolName) {
                    return tool;
                }
            }
        }

        return null;
    }
}

class AllowlistManager {
    constructor(configPath = null) {
        this.configPath = configPath || path.join('ai', 'supervisor', 'allowlists.json');
        this.allowlists = {};
        this.loadAllowlists();
    }

    loadAllowlists() {
        if (fs.existsSync(this.configPath)) {
            try {
                this.allowlists = JSON.parse(fs.readFileSync(this.configPath, 'utf8'));
            } catch (e) {
                console.error(`Error loading allowlists: ${e}`);
                this.allowlists = {};
            }
        } else {
            this.allowlists = {
                default: {
                    allow: [],
                    deny: [],
                    servers: []
                }
            };
            this.saveAllowlists();
        }
    }

    saveAllowlists() {
        const dir = path.dirname(this.configPath);
        if (!fs.existsSync(dir)) {
            fs.mkdirSync(dir, { recursive: true });
        }
        fs.writeFileSync(this.configPath, JSON.stringify(this.allowlists, null, 2), 'utf8');
    }

    getAllowedTools(agentId) {
        const agentConfig = this.allowlists[agentId] || {};
        const defaultConfig = this.allowlists.default || {};

        const allowed = new Set([
            ...(agentConfig.allow || []),
            ...(defaultConfig.allow || [])
        ]);
        const denied = new Set([
            ...(agentConfig.deny || []),
            ...(defaultConfig.deny || [])
        ]);

        // Deny takes precedence
        for (const item of denied) {
            allowed.delete(item);
        }

        return allowed;
    }

    getAllowedServers(agentId) {
        const agentConfig = this.allowlists[agentId] || {};
        const defaultConfig = this.allowlists.default || {};

        const agentServers = agentConfig.servers || [];
        const defaultServers = defaultConfig.servers || [];

        return agentServers.length > 0 ? agentServers : defaultServers;
    }

    isToolAllowed(agentId, toolId) {
        const allowedTools = this.getAllowedTools(agentId);

        if (allowedTools.has(toolId)) {
            return true;
        }

        // Check pattern matches
        for (const pattern of allowedTools) {
            if (pattern.includes('*')) {
                const prefix = pattern.replace('*', '');
                if (toolId.startsWith(prefix)) {
                    return true;
                }
            }
        }

        return false;
    }

    filterToolsByAllowlist(agentId, tools) {
        const allowedTools = this.getAllowedTools(agentId);
        const allowedServers = this.getAllowedServers(agentId);

        return tools.filter(tool => {
            const toolId = tool.tool_id || '';
            const server = tool.server || '';

            if (allowedServers.length > 0 && !allowedServers.includes(server)) {
                return false;
            }

            return this.isToolAllowed(agentId, toolId);
        });
    }
}

// CLI interface
if (require.main === module) {
    const args = process.argv.slice(2);
    const broker = new ToolBroker();

    // Simple CLI - can be extended
    if (args[0] === 'search' && args[1]) {
        const results = broker.searchTools(args[1], { maxResults: 10 });
        console.log(JSON.stringify(results, null, 2));
    } else {
        console.log('Usage: tool_broker.js search <query>');
    }
}

module.exports = { ToolBroker, ToolDiscovery, AllowlistManager };
