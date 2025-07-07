require('dotenv').config();

console.log('🔍 Environment Variables Debug\n');

console.log('CODA_API_TOKEN:', process.env.CODA_API_TOKEN ? '✅ Set' : '❌ Missing');
console.log('CODA_DOC_ID:', process.env.CODA_DOC_ID || '❌ Missing');
console.log('CODA_TABLE_ID:', process.env.CODA_TABLE_ID || '❌ Missing');

console.log('\n📝 Current values:');
console.log('API Token:', process.env.CODA_API_TOKEN ? process.env.CODA_API_TOKEN.substring(0, 10) + '...' : 'Not set');
console.log('Doc ID:', process.env.CODA_DOC_ID);
console.log('Table ID:', process.env.CODA_TABLE_ID); 