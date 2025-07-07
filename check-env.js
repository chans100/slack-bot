require('dotenv').config();

console.log('🔍 Checking Environment Variables\n');

console.log('CODA_API_TOKEN:', process.env.CODA_API_TOKEN ? 'Set' : 'NOT SET');
console.log('CODA_DOC_ID:', process.env.CODA_DOC_ID || 'NOT SET');
console.log('CODA_TABLE_ID:', process.env.CODA_TABLE_ID || 'NOT SET');
console.log('CODA_TABLE_ID2:', process.env.CODA_TABLE_ID2 || 'NOT SET');

console.log('\n📝 Full values:');
console.log('API Token:', process.env.CODA_API_TOKEN);
console.log('Doc ID:', process.env.CODA_DOC_ID);
console.log('Table ID:', process.env.CODA_TABLE_ID);
console.log('Table ID2:', process.env.CODA_TABLE_ID2); 