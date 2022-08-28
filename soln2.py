from web3 import Web3
import logging
import time
import requests
import sys
import pandas as pd

###Hardcoded values
uniswap_v2_factory_address = "0x5C69bEe701ef814a2B6a3EDD4B1652CB9cc5aA6f" #From https://docs.uniswap.org/protocol/V2/reference/smart-contracts/factory 
uniswap_v3_factory_address = "0x1F98431c8aD98523631AE4a59f267346ea31F984" #From https://docs.uniswap.org/protocol/reference/deployments

uniswap_v2_fee = 3000 #From https://docs.uniswap.org/protocol/V2/concepts/advanced-topics/fees
uniswap_v3_fee_list = [100, 500, 3000, 10000] #From https://docs.uniswap.org/protocol/concepts/V3-overview/fees

erc20_abi = open("erc20.abi").read() #Standard ERC20 ABI

uniswapv2_pair_abi = open("uniswapv2pair.abi").read() #UniSwap v2 pair contract ABI
uniswapv3_pool_abi = open("uniswapv3pool.abi").read() #UniSwap v3 pool contract ABI

uniswapv2_factory_abi = open("uniswapv2factory.abi").read() #UniSwap v2 factory contract ABI
uniswapv3_factory_abi = open("uniswapv3factory.abi").read() #UniSwap v3 factory contract ABI
###Hardcoded values


###Utility Functions
#Check if address is null
check_non_null_address = lambda addr : int(addr, base=16)!=0

#CSV Formatting for output with columns
def make_row_dict(uniswap_version, pool_addr, token0addr, token1addr, fee, token0usdprice, token1usdprice, token0amount, token1amount, pool_price):
	return {
		'uniswap_version' : uniswap_version,
		'pool_addr' : pool_addr,
		'token_0_addr': token0addr,
		'token_1_addr': token1addr,
		'fee_tier': fee/100.0,
		'token_0_amount' : token0amount,
		'token_1_amount' : token1amount,
		'token_0_usd_value' : token0amount * token0usdprice,
		'token_1_usd_value' : token1amount * token1usdprice,
		'pool_price_level' : pool_price,
		'token_0_usd_price': token0usdprice,
		'token_1_usd_price': token1usdprice,		
	}

#Function to get the USD price for all token addresses in a list from coingecko api
def get_coingecko_price_ethmainnet(tokenlist):
	url = "https://api.coingecko.com/api/v3/simple/token_price/ethereum?vs_currencies=USD&contract_addresses="+",".join(tokenlist)
	return requests.get(url).json()

#Function to extract USD price from coingecko json data for a given token. Returns nan if no suitable value found
def get_token_price_from_coingecko_data(token_addr, coingecko_data):
	if(token_addr.lower() in coingecko_data.keys()):
		if('usd' in coingecko_data[token_addr.lower()].keys()):
			return float(coingecko_data[token_addr.lower()]['usd'])
	return float('nan')

#Function to get a rpc conncetion object.
def get_rpc_connection(rpc_server_url="https://rpc.ankr.com/eth"):
	#Connceting to a HTTP RPC Node. A WSS or a local RPC node can also be used.
	try:
		rpc_connection = Web3(Web3.HTTPProvider(rpc_server_url))
	except Exception as ex:
		logging.error("RPC Node Error")
		return None
		
	if(not rpc_connection.isConnected()):
		print("RPC Node Error")
		return None
		
	return rpc_connection
###Utility Functions


###Main Function
def get_uniswap_data(token0addr, token1addr, output_filename, debug=False):
	#Get USD price for contracts
	coingecko_data = get_coingecko_price_ethmainnet([token0addr, token1addr])
	token0usdprice = get_token_price_from_coingecko_data(token0addr, coingecko_data)
	token1usdprice = get_token_price_from_coingecko_data(token1addr, coingecko_data)
	if(debug):
		print('USD Prices : ',token0usdprice, token1usdprice)
	
	#Get a rpc connection object
	rpc_connection = get_rpc_connection()
	if(type(rpc_connection)==type(None)):
		sys.exit()
	
	
	#Get Uniswap Factory objects
	uniswap_v2_factory_contract = rpc_connection.eth.contract(uniswap_v2_factory_address, abi=uniswapv2_factory_abi)
	uniswap_v3_factory_contract = rpc_connection.eth.contract(uniswap_v3_factory_address, abi=uniswapv3_factory_abi)
	
	if(debug):
		print("\n------\n")
		print(dir(uniswap_v2_factory_contract.functions))
		print( "\n------\n")
		print(dir(uniswap_v3_factory_contract.functions))
		print("\n------\n")
	
	
	token0contract = rpc_connection.eth.contract(token0addr, abi=erc20_abi)
	token1contract = rpc_connection.eth.contract(token1addr, abi=erc20_abi)
	
	token0decimals = token0contract.functions.decimals().call()
	token1decimals = token1contract.functions.decimals().call()
	
	
	#Array to store final dataset
	data = []

	#Uniswap v2 processing
	#Get pair address and check if it exists for the given tokens
	uniswap_v2_pair_addr = uniswap_v2_factory_contract.functions.getPair(token0addr, token1addr).call()
	#If non null value returned, process and add the data to the array
	if(check_non_null_address(uniswap_v2_pair_addr)):
		#Get contract for the pair
		uniswap_v2_pair_contract = rpc_connection.eth.contract(uniswap_v2_pair_addr, abi=uniswapv2_pair_abi)
		#Get reserve data
		reserves = uniswap_v2_pair_contract.functions.getReserves().call()
		#Check if token0 from input is token0 for pair contract. Make changes to ensure we get correct reserve values for the correct token by flipping if not.
		#Calculate human readable reserves
		uniswap_pair_v2_contract_token0 = uniswap_v2_pair_contract.functions.token0().call().lower()
		if(uniswap_pair_v2_contract_token0==token0addr.lower()):
			token0amount = reserves[0]/pow(10, token0decimals)
			token1amount = reserves[1]/pow(10, token1decimals)
		elif(uniswap_pair_v2_contract_token0==token1addr.lower()):
			token0amount = reserves[1]/pow(10, token0decimals)
			token1amount = reserves[0]/pow(10, token1decimals)
		else:
			#Should be one of these. Something wrong if it aint the case
			raise Exception
		#Calculate price
		pool_price = token1amount/token0amount
		#Add data to dataset
		data.append(make_row_dict(2, uniswap_v2_pair_addr, token0addr, token1addr, uniswap_v2_fee, token0usdprice, token1usdprice, token0amount, token1amount,  pool_price))
	
	#Uniswap v3 processing
	#Looping over all possible fee values in uniswap v3 fee schedule
	for fee in uniswap_v3_fee_list:
		#Get pool address and check if it exists for the given tokens
		uniswap_v3_pool_addr = uniswap_v3_factory_contract.functions.getPool(token0addr, token1addr, fee).call()
		#If non null value returned, process and add data to array
		if(check_non_null_address(uniswap_v3_pool_addr)):
			#Get contract for the pool
			uniswap_v3_pool_contract = rpc_connection.eth.contract(uniswap_v3_pool_addr, abi=uniswapv3_pool_abi)
			#Get slot0 data which has sqrtpricex96
			slot0_data = uniswap_v3_pool_contract.functions.slot0().call()
			#Check if token0 from input is token0 for pool contract. Make changes to ensure we get correct price values by flipping if not.
			#Calculate human readable prices
			
			uniswap_pool_v3_contract_token0 = uniswap_v3_pool_contract.functions.token0().call().lower()
			if(uniswap_pool_v3_contract_token0==token0addr.lower()):
				pool_price = slot0_data[0]*slot0_data[0]*pow(10, token0decimals-token1decimals)/pow(2,192)
			elif(uniswap_pool_v3_contract_token0==token1addr.lower()):
				pool_price = 1/(slot0_data[0]*slot0_data[0]*pow(10, token1decimals-token0decimals)/pow(2,192))
			else:
				#Should be one of these. Something wrong if it aint the case
				raise Exception
			
			#Get reserves for each token in the pool contract
			token0amount = token0contract.functions.balanceOf(uniswap_v3_pool_addr).call()/pow(10,token0decimals)
			token1amount = token1contract.functions.balanceOf(uniswap_v3_pool_addr).call()/pow(10,token1decimals)
			
			#add data to dataset
			data.append(make_row_dict(3, uniswap_v3_pool_addr, token0addr, token1addr, fee, token0usdprice, token1usdprice, token0amount, token1amount, pool_price))
	
	#Make dataframe. Easy to view and store
	dataframe = pd.DataFrame(data)
	print(dataframe.to_string())
	dataframe.to_csv(output_filename)
	
	
###Main Function
	

#Check if input parameters are correct. Must be 2 valid addresses. If either is not a valid address, the script terminates
if(len(sys.argv)<3):
	print("Usage : python3 soln2.py token0addr token1addr")
	sys.exit()

else:
	token0addr = sys.argv[1]
	token1addr = sys.argv[2]
	if(Web3.isAddress(token0addr) and Web3.isAddress(token1addr)):
		print("Addresses : ", token0addr, ",", token1addr)
	else:
		print("Address not valid")
		sys.exit()

get_uniswap_data(token0addr, token1addr, "output.csv", False)

#import code
#code.interact(local=locals())
