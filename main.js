const fs = require('fs');
const path = require('path');

const configPath = path.join(__dirname, 'config.json');
const defaultConfig = {
    // Define your default configuration values here
    key1: 'value1',
    key2: 'value2'
};

function checkAndCreateConfig() {
    if (!fs.existsSync(configPath)) {
        console.log('Config file not found. Creating a new one with default values.');
        fs.writeFileSync(configPath, JSON.stringify(defaultConfig, null, 2));
        return;
    }

    try {
        const configData = fs.readFileSync(configPath, 'utf8');
        JSON.parse(configData);
    } catch (error) {
        console.log('Config file is corrupted. Recreating with default values.');
        fs.writeFileSync(configPath, JSON.stringify(defaultConfig, null, 2));
    }
}

// Call the function at the start of your program
checkAndCreateConfig();

// ...existing code...
