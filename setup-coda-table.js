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

async function setupBlockerTable() {
  console.log('🔧 Setting up Blocker Table with Resolution Columns\n');
  
  const apiToken = process.env.CODA_API_TOKEN;
  const docId = process.env.CODA_DOC_ID;
  const blockerTableId = process.env.CODA_TABLE_ID2;
  
  if (!blockerTableId) {
    console.log('❌ No blocker table configured (CODA_TABLE_ID2 not set)');
    return;
  }
  
  console.log('Blocker Table ID:', blockerTableId);
  
  try {
    // First, check current table structure
    console.log('\n📊 Checking current table structure...');
    const tableUrl = `https://coda.io/apis/v1/docs/${docId}/tables/${blockerTableId}`;
    const tableResponse = await axios.get(tableUrl, {
      headers: {
        'Authorization': `Bearer ${apiToken}`
      }
    });
    
    console.log('✅ Table found:', tableResponse.data.name);
    
    // Get current columns
    const columnsUrl = `https://coda.io/apis/v1/docs/${docId}/tables/${blockerTableId}/columns`;
    const columnsResponse = await axios.get(columnsUrl, {
      headers: {
        'Authorization': `Bearer ${apiToken}`
      }
    });
    
    const existingColumns = columnsResponse.data.items.map(col => col.name);
    console.log('📋 Current columns:', existingColumns);
    
    // Define required resolution columns
    const requiredColumns = [
      { name: 'Status', type: 'text' },
      { name: 'Resolution Date', type: 'date' },
      { name: 'Resolved By', type: 'text' },
      { name: 'Resolution Notes', type: 'canvas' }
    ];
    
    // Check which columns are missing
    const missingColumns = requiredColumns.filter(col => !existingColumns.includes(col.name));
    
    if (missingColumns.length === 0) {
      console.log('✅ All resolution columns already exist!');
      return;
    }
    
    console.log('\n🔧 Adding missing columns...');
    
    // Add missing columns
    for (const column of missingColumns) {
      console.log(`Adding column: ${column.name} (${column.type})`);
      
      const addColumnUrl = `https://coda.io/apis/v1/docs/${docId}/tables/${blockerTableId}/columns`;
      const columnData = {
        name: column.name,
        format: {
          type: column.type
        }
      };
      
      try {
        const addResponse = await axios.post(addColumnUrl, columnData, {
          headers: {
            'Authorization': `Bearer ${apiToken}`,
            'Content-Type': 'application/json'
          }
        });
        
        console.log(`✅ Added column: ${column.name}`);
      } catch (error) {
        if (error.response?.status === 409) {
          console.log(`⚠️ Column ${column.name} already exists`);
        } else {
          console.log(`❌ Error adding column ${column.name}:`, error.response?.data?.message || error.message);
        }
      }
    }
    
    // Verify final structure
    console.log('\n📊 Verifying final table structure...');
    const finalColumnsResponse = await axios.get(columnsUrl, {
      headers: {
        'Authorization': `Bearer ${apiToken}`
      }
    });
    
    console.log('📋 Final columns:');
    finalColumnsResponse.data.items.forEach((column, index) => {
      console.log(`${index + 1}. ${column.name} (${column.format.type})`);
    });
    
    console.log('\n🎉 Blocker table setup complete!');
    
  } catch (error) {
    console.log('❌ Error:', error.response?.data?.message || error.message);
  }
}

setupCodaTable().catch(console.error);
setupBlockerTable(); 