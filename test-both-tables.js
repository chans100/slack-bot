require('dotenv').config();
const axios = require('axios');

async function testBothTables() {
  console.log('🧪 Testing Both Coda Tables\n');
  
  const apiToken = process.env.CODA_API_TOKEN;
  const docId = process.env.CODA_DOC_ID;
  const tableId = process.env.CODA_TABLE_ID;
  const blockerTableId = process.env.CODA_TABLE_ID2;
  
  console.log('Config:');
  console.log('Doc ID:', docId);
  console.log('Main Table ID:', tableId);
  console.log('Blocker Table ID:', blockerTableId);
  console.log('API Token:', apiToken ? '✅ Set' : '❌ Missing');
  
  // Test Main Table
  console.log('\n📊 Testing Main Table (mood responses)...');
  try {
    const mainTableUrl = `https://coda.io/apis/v1/docs/${docId}/tables/${tableId}/rows`;
    const mainTablePayload = {
      rows: [{
        cells: [
          { column: 'User ID', value: 'test-user-main' },
          { column: 'Response', value: '4' },
          { column: 'Timestamp', value: new Date().toISOString() }
        ]
      }]
    };
    
    const mainResponse = await axios.post(mainTableUrl, mainTablePayload, {
      headers: {
        'Authorization': `Bearer ${apiToken}`,
        'Content-Type': 'application/json'
      }
    });
    
    console.log('✅ Main table working! Row added:', mainResponse.data.addedRowIds[0]);
  } catch (error) {
    console.log('❌ Main table error:', error.response?.data?.message || error.message);
  }
  
  // Test Blocker Table (if configured)
  if (blockerTableId) {
    console.log('\n🚨 Testing Blocker Table...');
    try {
      const blockerTableUrl = `https://coda.io/apis/v1/docs/${docId}/tables/${blockerTableId}/rows`;
      const blockerPayload = {
        rows: [{
          cells: [
            { column: 'Blocker Description', value: 'Test blocker description' },
            { column: 'KR Name 2', value: 'Test KR' },
            { column: 'Urgency', value: 'medium' },
            { column: 'Notes', value: 'Test notes' }
          ]
        }]
      };
      
      const blockerResponse = await axios.post(blockerTableUrl, blockerPayload, {
        headers: {
          'Authorization': `Bearer ${apiToken}`,
          'Content-Type': 'application/json'
        }
      });
      
      console.log('✅ Blocker table working! Row added:', blockerResponse.data.addedRowIds[0]);
    } catch (error) {
      console.log('❌ Blocker table error:', error.response?.data?.message || error.message);
    }
  } else {
    console.log('\n⚠️ Blocker table not configured (CODA_TABLE_ID2 not set)');
  }
  
  console.log('\n🎉 Both tables test completed!');
}

testBothTables().catch(console.error); 