const fs = require('fs');
const path = require('path');

console.log('🔍 Detailed Environment Debug\n');

// Check if .env file exists
const envPath = path.join(__dirname, '.env');
console.log('Looking for .env file at:', envPath);
console.log('File exists:', fs.existsSync(envPath));

if (fs.existsSync(envPath)) {
  console.log('\n📄 .env file contents:');
  const envContent = fs.readFileSync(envPath, 'utf8');
  console.log(envContent);
}

console.log('\n📝 Environment variables:');
console.log('CODA_API_TOKEN:', process.env.CODA_API_TOKEN ? 'Set' : 'NOT SET');
console.log('CODA_DOC_ID:', process.env.CODA_DOC_ID || 'NOT SET');
console.log('CODA_TABLE_ID:', process.env.CODA_TABLE_ID || 'NOT SET');

// Try loading dotenv
try {
  require('dotenv').config();
  console.log('\n✅ dotenv loaded');
  console.log('After dotenv:');
  console.log('CODA_API_TOKEN:', process.env.CODA_API_TOKEN ? 'Set' : 'NOT SET');
  console.log('CODA_DOC_ID:', process.env.CODA_DOC_ID || 'NOT SET');
  console.log('CODA_TABLE_ID:', process.env.CODA_TABLE_ID || 'NOT SET');
} catch (error) {
  console.log('\n❌ Error loading dotenv:', error.message);
} 