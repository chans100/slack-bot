require('dotenv').config();
const axios = require('axios');

async function setupCodaTable() {
  console.log('🔧 Coda Table Setup Helper\n');
  
  const apiToken = process.env.CODA_API_TOKEN;
  const docId = process.env.CODA_DOC_ID;
  
  if (!apiToken || !docId) {
    console.log('❌ Missing Coda configuration. Please check your .env file.');
    return;
  }
  
  console.log('✅ Coda configuration found');
  console.log(`📄 Doc ID: ${docId}`);
  
  try {
    // Get all tables in the doc
    console.log('\n📋 Fetching tables from your Coda doc...');
    const tablesResponse = await axios.get(`https://coda.io/apis/v1/docs/${docId}/tables`, {
      headers: {
        'Authorization': `Bearer ${apiToken}`
      }
    });
    
    console.log('✅ Tables found:');
    tablesResponse.data.items.forEach((table, index) => {
      console.log(`${index + 1}. ${table.name} (ID: ${table.id})`);
    });
    
    // Check if we have the right columns in the first table
    if (tablesResponse.data.items.length > 0) {
      const firstTable = tablesResponse.data.items[0];
      console.log(`\n📊 Checking columns in table: ${firstTable.name}`);
      
      const columnsResponse = await axios.get(`https://coda.io/apis/v1/docs/${docId}/tables/${firstTable.id}`, {
        headers: {
          'Authorization': `Bearer ${apiToken}`
        }
      });
      
      const columns = columnsResponse.data.displayColumn ? [columnsResponse.data.displayColumn] : [];
      console.log('Current columns:');
      columns.forEach(col => {
        console.log(`- ${col.name}`);
      });
      
      console.log('\n📝 Required columns for Slack bot:');
      console.log('- User ID (Text)');
      console.log('- Response (Text)');
      console.log('- Timestamp (DateTime)');
      console.log('- Blocker Description (Text) - Optional');
      console.log('- KR Name (Text) - Optional');
      console.log('- Urgency (Text) - Optional');
      
      console.log('\n🔧 Next steps:');
      console.log('1. Go to your Coda doc');
      console.log('2. Create a table with the required columns above');
      console.log('3. Update your .env file with the correct TABLE_ID');
      console.log('4. Run this script again to verify');
      
    }
    
  } catch (error) {
    console.error('❌ Error:', error.response?.data || error.message);
  }
}

setupCodaTable().catch(console.error); 