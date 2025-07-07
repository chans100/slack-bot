require('dotenv').config();
const axios = require('axios');

async function testSimpleCoda() {
  console.log('🧪 Simple Coda Test (3 columns only)\n');
  
  const apiToken = process.env.CODA_API_TOKEN;
  const docId = process.env.CODA_DOC_ID;
  const tableId = process.env.CODA_TABLE_ID;
  
  console.log('Config:');
  console.log('Doc ID:', docId);
  console.log('Table ID:', tableId);
  console.log('API Token:', apiToken ? '✅ Set' : '❌ Missing');
  
  if (!apiToken || !docId || !tableId) {
    console.log('\n❌ Missing configuration');
    console.log('API Token:', apiToken);
    console.log('Doc ID:', docId);
    console.log('Table ID:', tableId);
    return;
  }
  
  try {
    // Test simple row addition with only 3 columns
    const url = `https://coda.io/apis/v1/docs/${docId}/tables/${tableId}/rows`;
    
    const payload = {
      rows: [{
        cells: [
          {
            column: 'User ID',
            value: 'test-user-123'
          },
          {
            column: 'Response',
            value: '5'
          },
          {
            column: 'Timestamp',
            value: new Date().toISOString()
          }
        ]
      }]
    };

    console.log('\n📝 Testing simple row addition...');
    console.log('URL:', url);
    const response = await axios.post(url, payload, {
      headers: {
        'Authorization': `Bearer ${apiToken}`,
        'Content-Type': 'application/json'
      }
    });

    console.log('✅ Success! Row added to Coda');
    console.log('Response:', response.data);
    
  } catch (error) {
    console.log('\n❌ Error:', error.response?.data || error.message);
  }
}

testSimpleCoda().catch(console.error); 