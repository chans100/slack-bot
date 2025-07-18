require('dotenv').config();
const axios = require('axios');

async function checkBlockerTable() {
  console.log('🔍 Checking Blocker Resolution Table Structure\n');
  
  const apiToken = process.env.CODA_API_TOKEN;
  const docId = process.env.CODA_DOC_ID;
  // Use the Blocker Resolution table ID that was found
  const blockerResTableId = 'grid-Kt4x0G2iIM';
  
  console.log('Blocker Resolution Table ID:', blockerResTableId);
  
  try {
    // Get table schema
    const schemaUrl = `https://coda.io/apis/v1/docs/${docId}/tables/${blockerResTableId}`;
    const schemaResponse = await axios.get(schemaUrl, {
      headers: {
        'Authorization': `Bearer ${apiToken}`
      }
    });
    
    console.log('✅ Table found:', schemaResponse.data.name);
    console.log('📊 Table columns:');
    
    // Get all columns
    const columnsUrl = `https://coda.io/apis/v1/docs/${docId}/tables/${blockerResTableId}/columns`;
    const columnsResponse = await axios.get(columnsUrl, {
      headers: {
        'Authorization': `Bearer ${apiToken}`
      }
    });
    
    columnsResponse.data.items.forEach((column, index) => {
      console.log(`${index + 1}. ${column.name} (${column.format.type}) - ID: ${column.id}`);
    });
    
    // Get sample data
    console.log('\n📊 Getting sample data...');
    const rowsUrl = `https://coda.io/apis/v1/docs/${docId}/tables/${blockerResTableId}/rows`;
    const rowsResponse = await axios.get(rowsUrl, {
      headers: {
        'Authorization': `Bearer ${apiToken}`
      }
    });
    
    if (rowsResponse.data.items && rowsResponse.data.items.length > 0) {
      console.log('\n📝 Sample row values:');
      const sampleRow = rowsResponse.data.items[0];
      for (const [key, value] of Object.entries(sampleRow.values)) {
        console.log(`   ${key}: ${value}`);
      }
    } else {
      console.log('   No rows found in table');
    }
    
  } catch (error) {
    console.log('❌ Error:', error.response?.data?.message || error.message);
  }
}

checkBlockerTable(); 