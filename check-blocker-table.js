require('dotenv').config();
const axios = require('axios');

async function checkBlockerTable() {
  console.log('🔍 Checking Blocker Table Structure\n');
  
  const apiToken = process.env.CODA_API_TOKEN;
  const docId = process.env.CODA_DOC_ID;
  const blockerTableId = process.env.CODA_TABLE_ID2;
  
  console.log('Blocker Table ID:', blockerTableId);
  
  if (!blockerTableId) {
    console.log('❌ No blocker table configured');
    return;
  }
  
  try {
    // Get table schema
    const schemaUrl = `https://coda.io/apis/v1/docs/${docId}/tables/${blockerTableId}`;
    const schemaResponse = await axios.get(schemaUrl, {
      headers: {
        'Authorization': `Bearer ${apiToken}`
      }
    });
    
    console.log('✅ Table found:', schemaResponse.data.name);
    console.log('📊 Table columns:');
    
    // Get all columns
    const columnsUrl = `https://coda.io/apis/v1/docs/${docId}/tables/${blockerTableId}/columns`;
    const columnsResponse = await axios.get(columnsUrl, {
      headers: {
        'Authorization': `Bearer ${apiToken}`
      }
    });
    
    columnsResponse.data.items.forEach((column, index) => {
      console.log(`${index + 1}. ${column.name} (${column.format})`);
    });
    
  } catch (error) {
    console.log('❌ Error:', error.response?.data?.message || error.message);
  }
}

checkBlockerTable().catch(console.error); 