# How to Set Up the SURF Research Cloud?

If you have access to the SURF Research Cloud, you can set it up to run with CHORAS. Follow the instructions below.

---

## Creating a Storage Unit

**Make sure to do this first, otherwise your workspace will not have any storage configured, and this cannot be changed later.**

1. Navigate to your SURF Research Cloud dashboard, and click on "Create new storage".
2. Select the SURF HPC Cloud option.
3. Select your desired storage size, and click on "Continue"
4. Give your storage a name. This is the name with which you will access the storage from within the Cloud runtime environment. Click on "Submit".

## Creating a Workspace

1. Navigate to your SURF Research Cloud dashboard, and click on "Create new workspace".
2. Scroll to the 4th page, and select the Singularity option. 
3. For the Singularity environment, you are automatically limited to only using the SURF HPC Cloud provider, with Ubuntu 22.04. 
4. When choosing the workspace size (number of cores and amount of RAM), we recommend at least 16GB of RAM, but this will depend on your available budget and the simulations you need to run.
5. Click "Continue".
6. If you have an available storage unit, you will now have the option to select storage. If not, create a storage unit, and restart the workspace creation process. Select your desired storage in this window. This storage will now be bound to and accessible from the workspace.
7. Click "Continue".
8. Set an expiry date, and give the workspace a name. 
9. Click "Submit". 

## SSH setup

1. To connect to the cloud, you will need to configure access via an SSH key. Use the following guide to generate a key: [https://docs.github.com/en/authentication/connecting-to-github-with-ssh/generating-a-new-ssh-key-and-adding-it-to-the-ssh-agent](https://docs.github.com/en/authentication/connecting-to-github-with-ssh/generating-a-new-ssh-key-and-adding-it-to-the-ssh-agent). 
2. Click on the "Profile" tab in the header of the SURF Research Cloud UI. 
3. Click on the "Public ssh key(s)" tab under your name.
4. Click on "Change SSH keys in profile page".
5. Click on "Add SSH key manually". 
6. You now need to copy the contents of your public key into the text input field provided. In macOS, you can follow the following instructions with the Terminal application, or with Git Bash if on Windows. Run the following command, where `<your_key_name>` indicates the name of the key (by default, this will be either `id_rsa`, or `id_ed25519`, depending on which kind of key you created), and `~/.ssh` is the default SSH key directory. Note that these files are hidden by default; you will not see them when navigating via the GUI. If you used a different directory when creating the keys, modify the command accordingly.

   ```bash
   pbcopy < ~/.ssh/<your_key_name>.pub
   ```
   This will copy the contents to the clipboard.

   **DO NOT forget the .pub extension; files without this are private keys, and should never be shared**.  
   
   If this does not work, use any other means you have to copy the entire contents of the `<your_key_name>.pub` to the clipboard.

7. Paste the contents into the input text field in the SURF Research Cloud Dashboard, and click on "Update".

## Testing SSH access

It can take a few minutes before your SSH key is added and works. Your computer might not have the ssh client installed by default; if this is the case, refer to this guide for how to install it: [https://gist.github.com/bityob/419ca30a766817640e717800b63d6862](https://gist.github.com/bityob/419ca30a766817640e717800b63d6862)
To test connection, run the following command in your terminal:
```bash
ssh <your_username>@<cloud_ip>
```
`<your_username>` is the username given to you by SURF, and can be seen in your profile (usually the first letter of your first name and your entire last name, all lowercase).
`<cloud-ip>` is the IP address of the cloud workspace. This can be found in the main SURF Research Cloud dashboard, under the "Workspaces" tab. Find your workspace, click the downward arrow, and look for an "IP Address" heading. 

When connecting for the first time, you will be prompted with something like:
```bash
   The authenticity of host 'example.com (192.168.1.1)' can't be established.
   ED25519 key fingerprint is SHA256:abc123...
   Are you sure you want to continue connecting (yes/no/[fingerprint])?  
```
Type in "yes" to continue.

You should now be fully authenticated, and can interact with the workspace's terminal.

If your storage has been properly configured, you should be able to access the storage folder under `/data/<your_storage_name>`. This is the same folder where CHORAS will be running simulations and writing results (see the Cloud Configuration section of the [CHORAS Setup Guide](setting_up_choras.md)).