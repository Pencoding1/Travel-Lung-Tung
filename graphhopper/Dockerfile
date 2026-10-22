ARG GRAPHHOPPER_BASE_IMAGE=israelhikingmap/graphhopper:latest
FROM ${GRAPHHOPPER_BASE_IMAGE}

COPY ./data/ /app_data/

ENTRYPOINT ["/bin/bash", "-c"]

CMD ["java -Ddw.graphhopper.datareader.file=/app_data/hcmc-latest.osm.pbf -Ddw.graphhopper.graph.location=/tmp/hcmc-gh -jar *.jar server /app_data/config.yml"]