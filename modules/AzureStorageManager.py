from azure.storage.blob import BlobServiceClient, BlobSasPermissions, generate_blob_sas
import os
import datetime as dt 

class AzureBlobStorageManager:
    def __init__(self, connection_str:str, container_name:str, download_dir="."):
        
        self.container_name = container_name
        
        self.blob_service_client = BlobServiceClient.from_connection_string(connection_str)
        self.container_client = self.blob_service_client.get_container_client(container_name)

        # The default directory to which to download a blob.
        self.download_dir = download_dir

    def upload_blob(self, file_name:str,  blob_name=None, overwrite=False) -> None:
        """Upload a local file to blob storage in Azure"""

        # Default blob_name = local filename 
        if blob_name is None:
            blob_name = os.path.basename(file_name)
        blob_client = self.container_client.get_blob_client(blob_name)
        
        try:
            # Upload the blob
            with open(file_name, "rb") as data:
                blob_client.upload_blob(data, overwrite=overwrite)
            print(f"Blob {blob_name} uploaded successfully.")
        except Exception as e: # Do something with this exception block (e.g. add logging)
            print(f"An error occurred: {str(e)}")

    def list_blobs(self, name_only=True) -> list: 
        """Wrapper to list blobs in the container"""
        blob_list = self.container_client.list_blobs()
        if name_only: 
            return [blob.name for blob in blob_list]
        else: 
            return list(blob_list)

    def download_blob(self, blob_name:str, download_path=None): 
        """Download a blob from the container. Local download path defaults to blob_name"""

        blob_client = self.container_client.get_blob_client(blob_name)

        if download_path is None:
            download_path = os.path.join(self.download_dir, os.path.basename(blob_name)) 
        
        with open(download_path, "wb") as file:
            download_bytes = blob_client.download_blob().readall()
            file.write(download_bytes)

    def has_blob(self, file_name:str) -> bool: 
        """Check if the container has a blob of the given name"""

        return os.path.basename(file_name) in self.list_blobs(name_only=True)
    
    def get_blob_last_modified(self, blob_name:str):
        """Get the last modified date of a blob in the storage container"""
        # Create a blob client
        blob_client =self.container_client.get_blob_client(blob_name)
       
        try:
            # Get blob properties
            blob_properties = blob_client.get_blob_properties()
            # Retrieve and print last modified date
            last_modified = blob_properties['last_modified']
            return last_modified.date()
           
        except Exception as e: # Do something with this exception block (e.g. add logging)
            print(f"An error occurred: {str(e)}")

        
    def get_blob_url(self, file_name:str, include_sas=False, expiry_hours=1) -> str:
        """Get the url of a blob in the storage container""" 

        blob_base = os.path.basename(file_name)
        blob_client = self.container_client.get_blob_client(blob=blob_base)
        
        url = blob_client.url 
        
        # Generate SAS token (read only)
        if include_sas: 
            expiry_time = dt.datetime.utcnow() + dt.timedelta(hours=expiry_hours)  # Adjust the expiration time as needed
            permissions = BlobSasPermissions(read=True)  # Adjust permissions as needed

            sas_token = generate_blob_sas(
            account_name=blob_client.account_name,
            container_name=self.container_name,
            blob_name=blob_base,
            account_key=blob_client.credential.account_key,
            permission=permissions,
            expiry=expiry_time,
            start=dt.datetime.utcnow(), 
            protocol='https'
            )

            url += f"?{sas_token}"

            print(blob_client.account_name)

        return url 
    