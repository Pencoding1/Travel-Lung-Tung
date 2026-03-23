# PayLoad Schema
``` json
Return POI: {
    "success": "bool", // Required
    "result": {
        "POI_ID": "str", // Required
        "POI_Name": "str", // Required
        "POI_Address": "str",// Required
        "POI_Description":{
            "insight": "str",
            "seo_article": "str",
            "review": {
                "rating": "float",
                "review": "str"
            }
        },
        "POI_Category": "str", // Required
        "POI_Contract_Info": {
            "website": ""str"",
            "fanpage": ""str"",
            "phonenumber": ""str""
        },
        "NEAR_BY":[
            {"poi": "POI_Object_Parsed_In_JSON", "distance": "float"},
            {"poi": "POI_Object_Parsed_In_JSON", "distance": "float"}, 
            {"poi": "POI_Object_Parsed_In_JSON", "distance": "float"}, 
            {"poi": "POI_Object_Parsed_In_JSON", "distance": "float"}, 
            {"poi": "POI_Object_Parsed_In_JSON", "distance": "float"}, 
            ...
        ], // Required (but can be empty list)
    }
}
```