const axios = require('axios');

class CodaIntegration {
  constructor() {
    this.apiToken = process.env.CODA_API_TOKEN;
    this.docId = process.env.CODA_DOC_ID;
    this.tableId = process.env.CODA_TABLE_ID;
    this.baseUrl = 'https://coda.io/apis/v1';
  }

  // Check if Coda is properly configured
  isConfigured() {
    return this.apiToken && this.docId && this.tableId;
  }

  // Add a new row to the Coda table
  async addResponse(userId, response, timestamp) {
    if (!this.isConfigured()) {
      console.warn('Coda not configured. Skipping response storage.');
      return false;
    }

    try {
      const url = `${this.baseUrl}/docs/${this.docId}/tables/${this.tableId}/rows`;
      
      const payload = {
        rows: [{
          cells: [
            {
              column: 'User ID',
              value: userId
            },
            {
              column: 'Response',
              value: response
            },
            {
              column: 'Timestamp',
              value: timestamp
            }
          ]
        }]
      };

      const apiResponse = await axios.post(url, payload, {
        headers: {
          'Authorization': `Bearer ${this.apiToken}`,
          'Content-Type': 'application/json'
        }
      });

      console.log('Response stored in Coda successfully:', apiResponse.data);
      return true;
    } catch (error) {
      console.error('Error storing response in Coda:', error.response?.data || error.message);
      return false;
    }
  }

  // Add structured blocker details to the Coda table
  async addBlockerDetails(userId, blockerData) {
    if (!this.isConfigured()) {
      console.warn('Coda not configured. Skipping blocker details storage.');
      return false;
    }

    try {
      const url = `${this.baseUrl}/docs/${this.docId}/tables/${this.tableId}/rows`;
      
      // Store blocker details as JSON in the Response column
      const blockerInfo = {
        type: 'blocked',
        blockerDescription: blockerData.blockerDescription,
        krName: blockerData.krName,
        urgency: blockerData.urgency
      };
      
      const payload = {
        rows: [{
          cells: [
            {
              column: 'User ID',
              value: userId
            },
            {
              column: 'Response',
              value: JSON.stringify(blockerInfo)
            },
            {
              column: 'Timestamp',
              value: blockerData.timestamp
            }
          ]
        }]
      };

      const apiResponse = await axios.post(url, payload, {
        headers: {
          'Authorization': `Bearer ${this.apiToken}`,
          'Content-Type': 'application/json'
        }
      });

      console.log('Blocker details stored in Coda successfully:', apiResponse.data);
      return true;
    } catch (error) {
      console.error('Error storing blocker details in Coda:', error.response?.data || error.message);
      return false;
    }
  }

  // Get all responses from the Coda table
  async getResponses() {
    if (!this.isConfigured()) {
      console.warn('Coda not configured. Cannot fetch responses.');
      return [];
    }

    try {
      const url = `${this.baseUrl}/docs/${this.docId}/tables/${this.tableId}/rows`;
      
      const response = await axios.get(url, {
        headers: {
          'Authorization': `Bearer ${this.apiToken}`
        }
      });

      return response.data.items || [];
    } catch (error) {
      console.error('Error fetching responses from Coda:', error.response?.data || error.message);
      return [];
    }
  }

  // Get table schema to validate column names
  async getTableSchema() {
    if (!this.isConfigured()) {
      console.warn('Coda not configured. Cannot fetch table schema.');
      return null;
    }

    try {
      const url = `${this.baseUrl}/docs/${this.docId}/tables/${this.tableId}`;
      
      const response = await axios.get(url, {
        headers: {
          'Authorization': `Bearer ${this.apiToken}`
        }
      });

      return response.data;
    } catch (error) {
      console.error('Error fetching table schema from Coda:', error.response?.data || error.message);
      return null;
    }
  }
}

module.exports = CodaIntegration; 