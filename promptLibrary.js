const fs = require('fs');
const path = require('path');

// List your prompt template files here
const templates = {
  blocker_interpretation: 'blocker_interpretation.md',
  sme_routing: 'sme_routing.md',
  kr_clarification: 'kr_clarification.md',
};

// Load all templates into memory
const loadedTemplates = {};
for (const [key, filename] of Object.entries(templates)) {
  loadedTemplates[key] = fs.readFileSync(path.join(__dirname, filename), 'utf-8');
}

/**
 * Fill placeholders in a template with values from a data object.
 * @param {string} templateKey - The key of the template to use.
 * @param {Object} data - An object with keys matching the placeholders (without curly braces).
 * @returns {string} The filled-in prompt.
 */
function fillTemplate(templateKey, data) {
  let prompt = loadedTemplates[templateKey];
  for (const [key, value] of Object.entries(data)) {
    const regex = new RegExp(`{{${key}}}`, 'g');
    prompt = prompt.replace(regex, value);
  }
  return prompt;
}

module.exports = {
  getTemplate: (key) => loadedTemplates[key],
  fillTemplate,
}; 